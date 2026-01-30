"""
Populator for registering all decorated tools in the database.

This scans the framework's known tool entry points (agent_tools, uierror module, gateway agent)
and inserts a record into the Tool table for each decorated function that does not
already exist.

Notes:
- The `Tool` model validates importability and that the target function is a decorated
  tool (instance of `DecoratedFunctionTool`) on construction.
- This populator is idempotent: existing tools (matched by name or fn_module) are skipped.
- After adding this file, remember to expose `populate_tools` in
  `database/populators/__init__.py` so it runs automatically on startup.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable

from sqlalchemy import Engine
from sqlmodel import Session, select
from strands.tools.decorator import DecoratedFunctionTool

from database.tools.models import Tool


def _gather_tool_functions() -> list[DecoratedFunctionTool]:  # pyright: ignore[reportMissingTypeArgument]
    """
    Collect all decorated tool functions that should be registered.

    Returns:
        List of DecoratedFunctionTool instances.
    """
    # Iterate over all agent_tools modules and collect decorated functions
    modules = [
        importlib.import_module("agent_tools"),
        importlib.import_module("gateway.agent"),
    ]

    tools: Iterable[DecoratedFunctionTool] = [  # pyright: ignore[reportMissingTypeArgument]
        fn
        for module in modules
        for fn in vars(module).values()
        if callable(fn) and isinstance(fn, DecoratedFunctionTool)
    ]

    return tools


def _tool_exists(session: Session, name: str, fn_module: str) -> bool:
    """
    Check if a tool already exists by name OR fn_module.

    Args:
        session: Active SQLModel session
        name: Tool name
        fn_module: Fully-qualified function path

    Returns:
        True if a matching record exists, False otherwise.
    """
    existing = session.exec(
        select(Tool).where((Tool.name == name) | (Tool.fn_module == fn_module))
    ).first()
    return existing is not None


def _compute_fn_module(fn: DecoratedFunctionTool) -> str:  # pyright: ignore[reportMissingTypeArgument]
    """
    Build the fully qualified module path + function name for storage.

    Args:
        fn: DecoratedFunctionTool instance

    Returns:
        String like 'package.subpackage.module.function_name'
    """
    module_name = getattr(fn._tool_func, "__module__", None)  # pyright: ignore[reportPrivateUsage]
    qualname = getattr(fn._tool_func, "__name__", None)  # pyright: ignore[reportPrivateUsage]
    if not module_name or not qualname:
        raise ValueError(f"Cannot compute module path for tool: {fn}")
    return f"{module_name}.{qualname}"


def populate_tools(engine: Engine) -> None:
    """
    Populate the Tool table with all decorated tools defined across the framework.

    Idempotent: skips creation when a tool already exists.

    Args:
        engine: SQLAlchemy engine used to open a session.
    """
    tool_functions = _gather_tool_functions()

    if not tool_functions:
        print("[populate_tools] No decorated tools found to register.")
        return

    created = 0
    skipped = 0
    errors: list[str] = []

    with Session(engine) as session:
        for decorated in tool_functions:
            try:
                name = decorated._tool_name  # pyright: ignore[reportPrivateUsage]
                description = decorated._tool_spec.get(  # pyright: ignore[reportPrivateUsage]
                    "description", "No description provided."
                )
                fn_module = _compute_fn_module(decorated)

                if _tool_exists(session, name, fn_module):
                    skipped += 1
                    continue

                # Create and add tool
                tool_record = Tool(
                    name=name,
                    description=description,
                    fn_module=fn_module,
                )
                session.add(tool_record)
                created += 1
            except Exception as e:
                errors.append(f"{getattr(decorated, 'name', 'UNKNOWN')} -> {e}")

        session.commit()

    print(
        f"[populate_tools] Completed. Created: {created}, Skipped: {skipped}, Errors: {len(errors)}"
    )
    if errors:
        for err in errors:
            print(f"[populate_tools][error] {err}")
