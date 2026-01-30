"""
JSON-driven populator for registering framework Agents into the database.

This replaces the previous hardcoded definitions and loads agent configurations
from a JSON file. Tool populators and router populators remain unchanged.

Notes:
- Idempotent: agents are only created if they do not already exist (matched by name).
- Tools must have been populated previously (populate_tools) or they will be skipped.
- Routers must exist for the specified model names in the JSON (use populate_routers first).
- Response model paths are stored as import strings for dynamic loading at runtime.
- Supports sub-agent relationships and tool attachments via JSON.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from database.agents.models import (
    Agent,
    AgentTool,
    AgentType,
    Argument,
    SubAgent,
)
from database.provider.models import Router
from database.tools.models import Tool
from settings import (
    PROVIDER_GROUNDING_MODEL,
    PROVIDER_MODEL,
    PROVIDER_VISION_MODEL,
    PROVIDER_VISION_TOOL_MODEL,
)


def _get_router_by_model(session: Session, model_name: str) -> Router:
    """
    Return an existing Router for the given model_name or panics.
    """
    router = session.exec(select(Router).where(Router.model_name == model_name)).first()
    if router:
        return router
    else:
        raise ValueError(
            f"[populate_agents] Error: No Router found for model '{model_name}'. Please create it first."
        )


def _argument(
    name: str,
    description: str,
    py_type: str,
    json_type: str,
) -> Argument:
    """Helper to create an Argument instance."""
    return Argument(
        name=name,
        description=description,
        type=py_type,
        json_type=json_type,
    )


def _attach_tools(
    session: Session,
    agent: Agent,
    tool_names: list[str],
    limits: list[int | None] | None = None,
) -> None:
    """
    Attach tools (by name) to an Agent via AgentTool association.
    Skips missing tools but logs a warning.
    When limits are provided, they must match the number of tools; each tool gets its corresponding limit.
    """

    if limits is not None and len(tool_names) != len(limits):
        raise ValueError(
            f"[populate_agents] Tools/limits length mismatch for agent '{agent.name}': \
            {len(tool_names)} tools vs {len(limits)} limits."
        )

    for idx, tool_name in enumerate(tool_names):
        tool = session.exec(select(Tool).where(Tool.name == tool_name)).first()
        if not tool:
            print(
                f"[populate_agents] Warning: Tool '{tool_name}' not found. Skipping for agent '{agent.name}'."
            )
            continue

        # Check if already associated
        if any(at.tool.id == tool.id for at in agent.tools):
            continue

        session.add(
            AgentTool(
                agent=agent,
                agent_id=agent.id,
                tool=tool,
                tool_id=tool.id,
                limit=(limits[idx] if limits is not None else None),
                required=False,
            )
        )


def _create_agent(
    session: Session,
    name: str,
    description: str,
    prompt: str | None,
    response_model: str | None,
    args: list[Argument],
    router: Router,
    agent_type: AgentType,
    input_type: Agent.InputType = Agent.InputType.TEXT,
    enabled: bool = True,
) -> Agent:
    """Create and persist an Agent if it doesn't already exist."""
    existing = session.exec(select(Agent).where(Agent.name == name)).first()
    if existing:
        return existing

    agent = Agent(
        name=name,
        description=description,
        prompt=prompt,
        response_model=response_model,
        input_type=input_type,
        enabled=enabled,
        router=router,
        type=agent_type,
        arguments=args,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    print(f"[populate_agents] Created agent '{name}'.")
    return agent


def _create_sub_agent(
    session: Session, parent: Agent, child: Agent, limit: int | None = None
) -> None:
    """Create a SubAgent relationship if not present."""
    existing = session.exec(
        select(SubAgent).where(
            SubAgent.parent_agent == parent, SubAgent.child_agent == child
        )
    ).first()
    if existing:
        return
    session.add(
        SubAgent(
            parent_agent_id=parent.id,
            parent_agent=parent,
            child_agent_id=child.id,
            child_agent=child,
            limit=limit,
        )
    )


def _resolve_input_type(value: str | None) -> Agent.InputType:
    if not value:
        return Agent.InputType.TEXT
    mapping = {
        "TEXT": Agent.InputType.TEXT,
        "IMAGETEXT": Agent.InputType.IMAGETEXT,
    }
    return mapping.get(value.upper(), Agent.InputType.TEXT)


def _resolve_agent_type(value: str) -> AgentType:
    mapping = {
        "GatewayAgent": AgentType.GatewayAgent,
        "ErrorAgent": AgentType.ErrorAgent,
        "GuiAgent": AgentType.GuiAgent,
    }
    if value not in mapping:
        raise ValueError(f"Unknown AgentType '{value}'.")
    return mapping[value]


def _load_json_config() -> dict[str, Any]:
    """
    Load agent configuration from adjacent JSON file:
    database/populators/agents.json

    Expected structure:
    {
      "agents": [
        {
          "name": "...",
          "description": "...",
          "prompt": "..." | null,
          "prompt_import": "package.module:CONST_OR_FUNC" | null,
          "response_model": "package.module.ClassName" | null,
          "router_model": "gpt-4o-mini" | "$PROVIDER_MODEL" | "$PROVIDER_VISION_MODEL" | "$PROVIDER_VISION_TOOL_MODEL" | "$PROVIDER_GROUNDING_MODEL",
          "agent_type": "GatewayAgent" | "ErrorAgent" | "GuiAgent",
          "input_type": "TEXT" | "IMAGETEXT",
          "enabled": true,
          "arguments": [
            {"name": "...", "description": "...", "type": "str", "json_type": "string"}
          ],
          "tools": {"names": ["take_screenshot"], "limits": [null]}
          }
        ],
      "sub_agents": [
        {"parent": "UI Exception Handler", "child": "UI Direct Recovery", "limit": 1}
      ]
    }
    """
    here = Path(__file__).parent
    cfg_path = here / "agents.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"[populate_agents] Missing JSON configuration file: {cfg_path}"
        )
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_router_model(model_token: str) -> str:
    """
    Translate special tokens into configured model names,
    otherwise pass through literal model names.
    """
    token_map = {
        "$PROVIDER_MODEL": PROVIDER_MODEL,
        "$PROVIDER_VISION_MODEL": PROVIDER_VISION_MODEL,
        "$PROVIDER_VISION_TOOL_MODEL": PROVIDER_VISION_TOOL_MODEL,
        "$PROVIDER_GROUNDING_MODEL": PROVIDER_GROUNDING_MODEL,
    }
    return token_map.get(model_token, model_token)


def _import_prompt(prompt_import: str) -> str:
    """
    Import prompt from 'package.module:ATTRIBUTE_OR_CALLABLE'.
    If callable, call it without args to get the prompt string.
    """
    module_name, _, attr = prompt_import.partition(":")
    if not module_name or not attr:
        raise ValueError(
            f"Invalid prompt_import '{prompt_import}'. Expected 'module:attr'"
        )
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    if callable(obj):
        raise ValueError("Prompt import functions are not supported in this context.")
    return str(obj)


def populate_agents(engine: Engine) -> None:
    """
    Populate the database with framework agents and their relationships from JSON.
    """
    cfg = _load_json_config()
    agents_cfg: list[dict[str, Any]] = cfg.get("agents", [])
    subs_cfg: list[dict[str, Any]] = cfg.get("sub_agents", [])

    if not agents_cfg:
        print("[populate_agents] No agents found in JSON configuration.")
        return

    with Session(engine) as session:
        # Create agents
        created_agents: dict[str, Agent] = {}

        for item in agents_cfg:
            name = item["name"]
            description = item.get("description", "") or ""
            prompt: str | None = item.get("prompt", None)
            prompt_import = item.get("prompt_import")
            if prompt_import and not prompt:
                prompt = _import_prompt(prompt_import)

            response_model = item.get("response_model")
            router_model_token = item.get("router_model", "$PROVIDER_MODEL")
            router_model_name = _resolve_router_model(router_model_token)
            router = _get_router_by_model(session, router_model_name)

            agent_type = _resolve_agent_type(item["agent_type"])
            input_type = _resolve_input_type(item.get("input_type"))
            enabled = bool(item.get("enabled", True))

            args_list = []
            for arg in item.get("arguments", []):
                args_list.append(
                    _argument(
                        name=arg["name"],
                        description=arg.get("description", ""),
                        py_type=arg.get("type", "str"),
                        json_type=arg.get("json_type", "string"),
                    )
                )

            agent = _create_agent(
                session=session,
                name=name,
                description=description,
                prompt=prompt,
                response_model=response_model,
                args=args_list,
                router=router,
                agent_type=agent_type,
                input_type=input_type,
                enabled=enabled,
            )
            created_agents[name] = agent

            # Tools
            tools_cfg = item.get("tools", {})
            tool_names = tools_cfg.get("names", []) or []
            tool_limits = tools_cfg.get("limits", None)
            if tool_names:
                _attach_tools(session, agent, tool_names, tool_limits)
        # Sub-agent relationships
        for rel in subs_cfg:
            parent_name = rel["parent"]
            child_name = rel["child"]
            limit = rel.get("limit")

            parent = session.exec(
                select(Agent).where(Agent.name == parent_name)
            ).first()
            child = session.exec(select(Agent).where(Agent.name == child_name)).first()
            if not parent or not child:
                print(
                    f"[populate_agents] Warning: SubAgent relation '{parent_name}' -> '{child_name}' skipped (missing agent)."
                )
                continue

            _create_sub_agent(session, parent, child, limit)

        session.commit()
        print("[populate_agents] Agent population from JSON complete.")
