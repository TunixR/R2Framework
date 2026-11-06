"""Tests for .github/scripts/conventions.py and the config files that share its vocabulary."""

import importlib.util
import os
import re
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GITHUB_DIR = REPO_ROOT / ".github"
SKIP_DIRS = {
    ".git",
    ".venv",
    ".worktrees",
    "__pycache__",
    ".ruff_cache",
    "htmlcov",
    "node_modules",
}


def _load_conventions() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "conventions", GITHUB_DIR / "scripts" / "conventions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conventions = _load_conventions()
AREAS: dict[str, list[str]] = conventions.load_areas()
SCOPES: list[str] = conventions.scopes(AREAS)


@pytest.mark.parametrize(
    "header",
    [
        "feat(agents): add agent polymorphism",
        "fix: save the reported result",
        "docs(observability): document the TooledGuiAgent span tree",
        "feat(recovery)!: send screenshots as binary frames",
        "chore(deps): bump the uv group across 1 directory with 2 updates",
        "fix(gui-agent): handle OTel context in the UI-TARS loop",
    ],
)
def test_valid_headers(header: str) -> None:
    assert conventions.check_header(header, SCOPES) == []


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("fix: Reported result saved correctly", "lowercase"),
        ("feat(wip): decision model agent", "unknown scope"),
        ("feature(agents): add x", "unknown type"),
        ("fix(agents): remove prints.", "period"),
        ("fix(agents):missing space", "is not"),
        ("Update README", "is not"),
        ("feat: " + "x" * 100, "characters"),
    ],
)
def test_invalid_headers(header: str, problem: str) -> None:
    errors = conventions.check_header(header, SCOPES)
    assert any(problem in error for error in errors), errors


def test_commit_message_body_and_git_generated() -> None:
    check = conventions.check_commit_message
    assert check("fix(db): keep seed ids\n\nRefs #12\n# comment\n", SCOPES) == []
    assert check("fix(db): keep seed ids\nno blank line\n", SCOPES) != []
    assert check("Merge branch 'develop' into fix/1-x\n", SCOPES) == []
    assert check('Revert "feat: x"\n', SCOPES) == []


def test_pr_labels_from_title() -> None:
    add, remove = conventions.pr_labels(
        "feat(recovery)!: change the payload",
        "",
        ["type: bug", "type: security", "area: db"],
    )
    assert add == {"type: feature", "breaking"}
    assert remove == {
        "type: bug"
    }  # manual `type: security` and area labels are untouched


def test_pr_labels_breaking_footer_deps_and_invalid_title() -> None:
    add, _ = conventions.pr_labels(
        "chore(deps): bump x", "BREAKING CHANGE: drops y", []
    )
    assert add == {"type: chore", "dependencies", "breaking"}
    _, remove = conventions.pr_labels("fix: x", "", ["breaking", "type: bug"])
    assert remove == {"breaking"}
    assert conventions.pr_labels("Some title", "", ["type: bug"]) == (set(), set())


def test_issue_labels_from_form_and_paths() -> None:
    body = (
        "### Where\n\n`routers/recovery.py:120` and "
        "https://github.com/TunixR/R2Framework/blob/develop/database/agents/uitars.py#L10\n\n"
        "### Area\n\nauth, deps, nonsense\n"
    )
    added = conventions.issue_labels(body, ["area: auth"], AREAS)
    assert added == {
        "dependencies",
        "area: recovery",
        "area: agents",
        "area: gui-agent",
    }


def test_issue_labels_cross_cutting_and_empty_form() -> None:
    many = " ".join(
        ["routers/recovery.py", "security/", "docker/README.md", "s3/utils.py"]
    )
    body = f"{many}\n\n### Area\n\n_No response_\n"
    assert conventions.issue_labels(body, [], AREAS) == set()


def test_event_labels_dispatch() -> None:
    event = {
        "issue": {"number": 7, "title": "x", "body": "see `s3/utils.py`", "labels": []}
    }
    assert conventions.event_labels(event, AREAS) == {
        "number": 7,
        "add": ["area: tracing"],
        "remove": [],
    }


def test_every_labeler_glob_matches_a_tracked_path() -> None:
    files: list[str] = []
    for root, dirs, names in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(root).relative_to(REPO_ROOT).as_posix()
        files += [name if rel == "." else f"{rel}/{name}" for name in names]
    optional = {"experiment_files/**"}  # git-ignored, may not exist in a checkout
    for label, globs in AREAS.items():
        for glob in globs:
            if glob in optional:
                continue
            regex = re.escape(glob).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
            assert any(re.fullmatch(regex, f) for f in files), (
                f"{label}: {glob} matches nothing"
            )


def test_vocabulary_is_consistent_across_config() -> None:
    labels = {
        entry["name"]
        for entry in yaml.safe_load(
            (GITHUB_DIR / "labels.yml").read_text(encoding="utf-8")
        )
    }
    derived = set(AREAS) | set(conventions.TYPE_LABELS.values())
    derived |= {conventions.DEPS_LABEL, conventions.BREAKING_LABEL}
    derived |= set(conventions.MANUAL_TYPE_LABELS)
    assert derived <= labels, f"missing from labels.yml: {derived - labels}"
    area_labels = {
        label for label in labels if label.startswith(conventions.AREA_PREFIX)
    }
    assert area_labels == set(AREAS), "labels.yml and labeler.yml list different areas"

    for form in (GITHUB_DIR / "ISSUE_TEMPLATE").glob("*.yml"):
        if form.name == "config.yml":
            continue
        config = yaml.safe_load(form.read_text(encoding="utf-8"))
        assert set(config["labels"]) <= labels, form.name
        (area,) = [field for field in config["body"] if field.get("id") == "area"]
        assert area["attributes"]["options"] == SCOPES, f"{form.name}: Area dropdown"

    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for scope in SCOPES:
        assert f"| `{scope}` |" in contributing, (
            f"CONTRIBUTING.md areas table lacks {scope}"
        )
    for kind in conventions.TYPE_LABELS:
        assert f"`{kind}`" in contributing, f"CONTRIBUTING.md lacks type {kind}"


def test_issue_labels_keep_dominant_areas_only() -> None:
    body = (
        "`database/agents/models.py`, `database/agents/base.py`, `gateway/agent.py`, "
        "`prompts/gui_agent.py` and, once, `evals/run_recovery_eval.py`. See ARCHITECTURE.md "
        "and OBSERVABILITY.md."
    )
    assert conventions.issue_labels(body, [], AREAS) == {"area: agents"}
