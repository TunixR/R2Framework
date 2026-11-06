"""Repository conventions: commit and PR-title checks, and automatic issue/PR labels.

One vocabulary for *what kind of change* (commit types, below) and *which part of the system*
(areas, the `area: ...` keys of `.github/labeler.yml`). See CONTRIBUTING.md.

Subcommands:
    check-commit <file>   commit-msg hook (pre-commit): validate a commit message.
    check-title <title>   CI: validate a PR title, which becomes the squash commit.
    labels <event.json>   CI: print the labels to add/remove for a GitHub issue or PR event,
                          as JSON `{"number": N, "add": [...], "remove": [...]}`.

Labels it decides:
    PRs:    `type: ...` from the title's type, `breaking` from `!` or a `BREAKING CHANGE:` footer,
            `dependencies` for the `deps` scope. `area: ...` comes from changed files (actions/labeler).
    Issues: `area: ...` from the issue form's "Area" dropdown and from repo paths the body mentions.
            `type: ...` comes from the issue form itself. Issue labels are only ever added.

Only depends on PyYAML (run in CI with `uv run --no-project --with pyyaml`).
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELER_FILE = REPO_ROOT / ".github" / "labeler.yml"

# Commit type -> `type:` label. `type: security` is never derived; it is applied by hand.
TYPE_LABELS: dict[str, str] = {
    "feat": "type: feature",
    "fix": "type: bug",
    "refactor": "type: refactor",
    "perf": "type: perf",
    "test": "type: test",
    "docs": "type: docs",
    "build": "type: chore",
    "ci": "type: chore",
    "chore": "type: chore",
    "revert": "type: chore",
}
MANUAL_TYPE_LABELS = frozenset({"type: security"})
AREA_PREFIX = "area: "
DEPS_SCOPE = "deps"
DEPS_LABEL = "dependencies"
BREAKING_LABEL = "breaking"

MAX_HEADER_LENGTH = 100  # hard limit; CONTRIBUTING.md asks for <= 72
# Areas inferred from the paths an issue mentions: rank areas by how many distinct paths point at
# them and keep the top ones (at most MAX_INFERRED_AREAS, each with at least DOMINANCE x the top
# count), so a long issue that cites files from everywhere is labelled by what it is mostly about.
MAX_INFERRED_AREAS = 3
DOMINANCE = 0.5

HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()]*)\))?(?P<breaking>!)?: (?P<subject>.*)$"
)
# `Added ...` is rejected; acronyms and identifiers (`OTel`, `TooledGuiAgent`, `S3`) are not.
CAPITALISED_WORD_RE = re.compile(r"[A-Z][a-z]+(?![A-Za-z0-9])")
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
# Git-generated messages that the commit-msg hook lets through.
GIT_GENERATED_RE = re.compile(r'^(Merge |Revert "|fixup! |squash! |amend! )')
# Candidate repo paths in free text: `a/b.py`, a/b/, file.md, GitHub blob/tree URLs.
URL_PATH_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/(?:blob|tree)/[^/\s]+/(\S+)"
)
PATH_TOKEN_RE = re.compile(
    r"[\w.-]*(?:/[\w.*-]+)+/?|[\w.-]+/|[\w-]+\.(?:py|md|ya?ml|toml|ini|lock)\b"
)


def load_areas(labeler_file: Path = LABELER_FILE) -> dict[str, list[str]]:
    """Return {label: globs} for every label in labeler.yml (areas and `dependencies`)."""
    config = yaml.safe_load(labeler_file.read_text(encoding="utf-8"))
    areas: dict[str, list[str]] = {}
    for label, rules in config.items():
        globs: list[str] = []
        for rule in rules:
            for matcher in rule.get("changed-files", []):
                value = matcher.get("any-glob-to-any-file", [])
                globs.extend([value] if isinstance(value, str) else value)
        areas[label] = globs
    return areas


def scopes(areas: Mapping[str, object]) -> list[str]:
    """Valid commit scopes: every area name, plus `deps`."""
    names = [
        label.removeprefix(AREA_PREFIX)
        for label in areas
        if label.startswith(AREA_PREFIX)
    ]
    return [*names, DEPS_SCOPE]


def scope_label(scope: str) -> str:
    return DEPS_LABEL if scope == DEPS_SCOPE else f"{AREA_PREFIX}{scope}"


def check_header(header: str, valid_scopes: Sequence[str]) -> list[str]:
    """Problems with a Conventional Commit header (`<type>(<scope>)!: <subject>`)."""
    match = HEADER_RE.match(header)
    if match is None:
        return [
            f"{header!r} is not `<type>(<area>)!: <summary>` "
            "(scope and `!` optional, one space after the colon)"
        ]
    errors: list[str] = []
    kind, scope, subject = match["type"], match["scope"], match["subject"]
    if kind not in TYPE_LABELS:
        errors.append(f"unknown type {kind!r}; use one of: {', '.join(TYPE_LABELS)}")
    if scope is not None and scope not in valid_scopes:
        errors.append(
            f"unknown scope {scope!r}; use one area from .github/labeler.yml "
            f"({', '.join(valid_scopes)}) or no scope for cross-cutting changes"
        )
    if not subject.strip():
        errors.append("empty summary")
    elif CAPITALISED_WORD_RE.match(subject):
        errors.append(
            "summary should start lowercase (imperative: `add ...`, not `Added ...`)"
        )
    if subject.endswith("."):
        errors.append("summary should not end with a period")
    if len(header) > MAX_HEADER_LENGTH:
        errors.append(
            f"header is {len(header)} characters; keep it under 72 (hard limit 100)"
        )
    return errors


def check_commit_message(message: str, valid_scopes: Sequence[str]) -> list[str]:
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    header = next((line for line in lines if line.strip()), "")
    if GIT_GENERATED_RE.match(header):
        return []
    errors = check_header(header, valid_scopes)
    body_start = lines.index(header) + 1
    if len(lines) > body_start and lines[body_start].strip():
        errors.append("leave a blank line between the header and the body")
    return errors


def pr_labels(
    title: str, body: str, current: Iterable[str]
) -> tuple[set[str], set[str]]:
    """Labels to add and remove for a PR, from its Conventional Commit title."""
    current_set = set(current)
    match = HEADER_RE.match(title)
    if match is None or match["type"] not in TYPE_LABELS:
        return (
            set(),
            set(),
        )  # the title check reports it; leave labels alone until it is fixed
    wanted = {TYPE_LABELS[match["type"]]}
    if match["scope"] == DEPS_SCOPE:
        wanted.add(DEPS_LABEL)
    breaking = (
        match["breaking"] is not None or BREAKING_FOOTER_RE.search(body) is not None
    )
    if breaking:
        wanted.add(BREAKING_LABEL)
    stale = {
        label
        for label in current_set
        if label.startswith("type: ")
        and label not in MANUAL_TYPE_LABELS
        and label not in wanted
    }
    if not breaking and BREAKING_LABEL in current_set:
        stale.add(BREAKING_LABEL)
    return wanted - current_set, stale


def form_section(body: str, heading: str) -> str | None:
    """The text under `### <heading>` in an issue-form body, or None."""
    match = re.search(
        rf"^###\s+{re.escape(heading)}\s*$(.*?)(?=^###\s|\Z)", body, re.M | re.S
    )
    if match is None:
        return None
    text = match[1].strip()
    return None if text in ("", "_No response_") else text


def mentioned_paths(text: str) -> set[str]:
    paths: set[str] = set()
    stripped = URL_PATH_RE.sub(" ", text)
    for token in [*URL_PATH_RE.findall(text), *PATH_TOKEN_RE.findall(stripped)]:
        token = re.sub(r"(:\d+)+$|#L\d+.*$", "", token).removeprefix("./")
        if token and not token.startswith(("http", "//")):
            paths.add(token)
    return paths


def areas_for_paths(
    paths: Iterable[str], areas: Mapping[str, list[str]]
) -> Counter[str]:
    """How many of `paths` fall in each area. Top-level docs (`ARCHITECTURE.md`, ...) are
    ignored: issues cite them for context, not because the change is about them."""
    found: Counter[str] = Counter()
    for path in paths:
        if "/" not in path and path.endswith(".md"):
            continue
        candidates = (path, path.rstrip("/") + "/")
        for label, globs in areas.items():
            if any(fnmatchcase(c, g) for c in candidates for g in globs):
                found[label] += 1
    return found


def dominant_areas(counts: Counter[str]) -> set[str]:
    if not counts:
        return set()
    ranked = counts.most_common()
    threshold = ranked[0][1] * DOMINANCE
    top = [(label, n) for label, n in ranked if n >= threshold]
    if len(top) > MAX_INFERRED_AREAS:
        # Cut below the first count that doesn't fit, so ties are kept or dropped together;
        # many areas mentioned equally often (cross-cutting) gives no label.
        cutoff = top[MAX_INFERRED_AREAS][1]
        top = [(label, n) for label, n in top if n > cutoff]
    return {label for label, _ in top}


def issue_labels(
    body: str, current: Iterable[str], areas: Mapping[str, list[str]]
) -> set[str]:
    """Labels to add to an issue: areas chosen in the form, plus areas of the paths it mentions."""
    valid = set(scopes(areas))
    wanted: set[str] = set()
    chosen = form_section(body, "Area")
    if chosen:
        wanted |= {
            scope_label(s.strip()) for s in chosen.split(",") if s.strip() in valid
        }
    wanted |= dominant_areas(areas_for_paths(mentioned_paths(body), areas))
    return wanted - set(current)


def event_labels(
    event: Mapping[str, object], areas: Mapping[str, list[str]]
) -> dict[str, object]:
    item = event.get("pull_request") or event.get("issue")
    if not isinstance(item, dict):
        raise SystemExit("event has neither `pull_request` nor `issue`")
    current = [label["name"] for label in item.get("labels") or []]
    title, body = item.get("title") or "", item.get("body") or ""
    if "pull_request" in event:
        add, remove = pr_labels(title, body, current)
    else:
        add, remove = issue_labels(body, current, areas), set()
    return {"number": item["number"], "add": sorted(add), "remove": sorted(remove)}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("check-commit", "check-title", "labels"):
        print(__doc__, file=sys.stderr)
        return 2
    command, arg = argv
    areas = load_areas()
    if command == "labels":
        event = json.loads(Path(arg).read_text(encoding="utf-8"))
        print(json.dumps(event_labels(event, areas)))
        return 0
    if command == "check-commit":
        errors = check_commit_message(
            Path(arg).read_text(encoding="utf-8"), scopes(areas)
        )
        what = "commit message"
    else:
        errors = check_header(arg.strip(), scopes(areas))
        what = "PR title"
    for error in errors:
        print(f"{what}: {error}", file=sys.stderr)
    if errors:
        print("See CONTRIBUTING.md -> Commits.", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
