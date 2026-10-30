from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from database.provider.models import Router
from settings import (
    FREE_PROVIDER_API_KEY,
    PROVIDER_API_BASE,
    PROVIDER_API_KEY,
    PROVIDER_GROUNDING_MODEL,
    PROVIDER_GROUNDING_MODEL_BACKBONE,
    PROVIDER_MODEL,
    PROVIDER_VISION_MODEL,
    PROVIDER_VISION_TOOL_MODEL,
)


def _existing_router(
    session: Session, model_name: str, api_endpoint: str
) -> Router | None:
    """
    Return an existing Router matching model_name + api_endpoint, or None.
    """
    return session.exec(
        select(Router).where(
            (Router.model_name == model_name) & (Router.api_endpoint == api_endpoint)
        )
    ).first()


def _create_router(
    session: Session,
    api_key: str,
    model_name: str,
    api_endpoint: str,
    provider_type: Router.Provider | None = None,
    capabilities: list[Router.Capability] | None = None,
    vision_backbone: Router.VisionBackbone | None = None,
) -> Router:
    """
    Create and persist a Router record.
    """
    router = Router(
        api_key=api_key,
        model_name=model_name,
        api_endpoint=api_endpoint,
        provider_type=provider_type or Router.Provider.OPENROUTER,
        capabilities=capabilities or [Router.Capability.TEXT],
        vision_backbone=vision_backbone,
    )
    session.add(router)
    session.commit()
    session.refresh(router)
    print(f"[populate_routers] Created router for model '{model_name}'.")
    return router


def _load_json_config() -> dict[str, Any]:
    """
    Load router configuration from adjacent JSON file:
    database/populators/routers.json

    Expected structure:
    {
      "routers": [
        {
          "model_name": "$PROVIDER_MODEL" | "$PROVIDER_VISION_MODEL" | "$PROVIDER_VISION_TOOL_MODEL" | "$PROVIDER_GROUNDING_MODEL" | "literal-model-name",
          "api_key": "$FREE_PROVIDER_API_KEY" | "$PROVIDER_API_KEY" | "literal-api-key",
          "api_endpoint": "$PROVIDER_API_BASE" | "https://api.example.com/v1",
          "provider_type": "OPENROUTER",  // optional, defaults to OPENROUTER
          "capabilities": ["TEXT", "VISION"],  // optional, defaults to ["TEXT"]
          "vision_backbone": "QWEN3.5"  // optional, defaults to OTHER for vision routers
        }
      ]
    }
    """
    here = Path(__file__).parent
    cfg_path = here / "routers.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"[populate_routers] Missing JSON configuration file: {cfg_path}"
        )
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_token(value: str) -> str:
    """
    Resolve known tokens to values from settings, otherwise return the literal.
    """
    token_map = {
        "$FREE_PROVIDER_API_KEY": FREE_PROVIDER_API_KEY,
        "$PROVIDER_API_KEY": PROVIDER_API_KEY,
        "$PROVIDER_API_BASE": PROVIDER_API_BASE,
        "$PROVIDER_MODEL": PROVIDER_MODEL,
        "$PROVIDER_VISION_MODEL": PROVIDER_VISION_MODEL,
        "$PROVIDER_VISION_TOOL_MODEL": PROVIDER_VISION_TOOL_MODEL,
        "$PROVIDER_GROUNDING_MODEL": PROVIDER_GROUNDING_MODEL,
        "$PROVIDER_GROUNDING_MODEL_BACKBONE": PROVIDER_GROUNDING_MODEL_BACKBONE,
    }
    return token_map.get(value, value)


def _resolve_provider_type(name: str | None) -> Router.Provider | None:
    if not name:
        return None
    upper = name.upper()
    # Extend here if more providers are supported in Router.Provider enum
    if upper == "OPENROUTER":
        return Router.Provider.OPENROUTER
    if upper == "OPENAI":
        return Router.Provider.OPENAI
    if upper == "VLLM":
        return Router.Provider.VLLM
    raise ValueError(f"Unknown provider_type '{name}'.")


def _resolve_capabilities(values: list[str] | None) -> list[Router.Capability]:
    """Resolve configured capability names, defaulting to text-only."""
    if not values:
        return [Router.Capability.TEXT]

    capabilities: list[Router.Capability] = []
    for value in values:
        try:
            capability = Router.Capability(value.upper())
        except ValueError as e:
            raise ValueError(f"Unknown router capability '{value}'.") from e
        if capability not in capabilities:
            capabilities.append(capability)
    return capabilities


def _resolve_vision_backbone(name: str | None) -> Router.VisionBackbone | None:
    """Resolve a configured vision backbone name, if any."""
    if not name:
        return None
    try:
        return Router.VisionBackbone(name.upper())
    except ValueError as e:
        raise ValueError(f"Unknown vision backbone '{name}'.") from e


def populate_routers(engine: Engine) -> None:
    """
    Populate Router entries based on JSON configuration.
    Skips creation if a router already exists for (model_name, api_endpoint).
    """

    cfg = _load_json_config()
    routers_cfg = cfg.get("routers", [])
    if not routers_cfg:
        print("[populate_routers] No routers found in JSON configuration.")
        return

    created = 0
    skipped = 0
    with Session(engine) as session:
        for item in routers_cfg:
            model_name = _resolve_token(item["model_name"])
            api_key = _resolve_token(item["api_key"])
            api_endpoint = _resolve_token(item["api_endpoint"])
            provider_type = _resolve_provider_type(item.get("provider_type"))
            capabilities = _resolve_capabilities(item.get("capabilities"))
            vision_backbone = _resolve_vision_backbone(item.get("vision_backbone"))

            if _existing_router(session, model_name, api_endpoint):
                skipped += 1
                continue

            _ = _create_router(
                session,
                api_key=api_key,
                model_name=model_name,
                api_endpoint=api_endpoint,
                provider_type=provider_type,
                capabilities=capabilities,
                vision_backbone=vision_backbone,
            )
            created += 1

    print(
        f"[populate_routers] Completed. Created: {created}, Skipped (already existed): {skipped}"
    )
