from __future__ import annotations

from typing import Any

import pyautogui
import pyperclip

from .models import ActionResult


def _center_to_pixels(start_box: Any) -> tuple[int, int]:
    if not isinstance(start_box, list):
        raise ValueError("start_box must be a list")
    if len(start_box) == 2:
        x1 = x2 = float(start_box[0])
        y1 = y2 = float(start_box[1])
    elif len(start_box) == 4:
        x1 = float(start_box[0])
        y1 = float(start_box[1])
        x2 = float(start_box[2])
        y2 = float(start_box[3])
    else:
        raise ValueError("start_box must have length 2 or 4")

    width, height = pyautogui.size()
    x = int(((x1 + x2) / 2.0) * width)
    y = int(((y1 + y2) / 2.0) * height)
    return x, y


def _drag_to_pixels(start_box: Any, end_box: Any) -> tuple[int, int, int, int]:
    sx, sy = _center_to_pixels(start_box)
    ex, ey = _center_to_pixels(end_box)
    return sx, sy, ex, ey


def execute_action(action: dict[str, Any], dry_run: bool = False) -> ActionResult:
    action_type = str(action.get("action_type", "unknown"))
    action_inputs = action.get("action_inputs", {})

    try:
        if not isinstance(action_inputs, dict):
            raise ValueError("action_inputs must be an object")

        if dry_run:
            return ActionResult(success=True, action_type=action_type)

        if action_type in {"click", "left_single"}:
            x, y = _center_to_pixels(action_inputs.get("start_box"))
            pyautogui.click(x=x, y=y, button="left")
        elif action_type == "left_double":
            x, y = _center_to_pixels(action_inputs.get("start_box"))
            pyautogui.doubleClick(x=x, y=y, button="left")
        elif action_type == "right_single":
            x, y = _center_to_pixels(action_inputs.get("start_box"))
            pyautogui.click(x=x, y=y, button="right")
        elif action_type == "hover":
            x, y = _center_to_pixels(action_inputs.get("start_box"))
            pyautogui.moveTo(x=x, y=y)
        elif action_type in {"drag", "select"}:
            sx, sy, ex, ey = _drag_to_pixels(
                action_inputs.get("start_box"),
                action_inputs.get("end_box"),
            )
            pyautogui.moveTo(x=sx, y=sy)
            pyautogui.dragTo(x=ex, y=ey, duration=1.0)
        elif action_type == "scroll":
            direction = str(action_inputs.get("direction", "")).lower()
            start_box = action_inputs.get("start_box")
            amount = 5 if "up" in direction else -5
            if start_box is None:
                pyautogui.scroll(amount)
            else:
                x, y = _center_to_pixels(start_box)
                pyautogui.scroll(amount, x=x, y=y)
        elif action_type == "hotkey":
            hotkey = str(action_inputs.get("hotkey") or action_inputs.get("key") or "")
            keys = [k for k in hotkey.split(" ") if k]
            if not keys:
                raise ValueError("hotkey requires one or more keys")
            pyautogui.hotkey(*keys)
        elif action_type in {"keydown", "press"}:
            key = str(action_inputs.get("key") or action_inputs.get("press") or "")
            if not key:
                raise ValueError("keydown requires a key")
            pyautogui.keyDown(key)
        elif action_type in {"keyup", "release"}:
            key = str(action_inputs.get("key") or action_inputs.get("press") or "")
            if not key:
                raise ValueError("keyup requires a key")
            pyautogui.keyUp(key)
        elif action_type == "type":
            content = str(action_inputs.get("content") or "")
            pyperclip.copy(content.rstrip("\n"))
            pyautogui.hotkey("ctrl", "v")
            if content.endswith("\n"):
                pyautogui.press("enter")
        else:
            raise ValueError(f"Unsupported action_type: {action_type}")

        return ActionResult(success=True, action_type=action_type)
    except Exception as exc:
        return ActionResult(success=False, action_type=action_type, error=str(exc))
