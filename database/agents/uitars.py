"""UITARS Action Specification
This module provides grounding and execution for UI automation actions predicted by a vision-language grounding model (UITARS).
The model outputs a textual reasoning block followed by one or more structured Action definitions that are parsed into a normalized
internal structure, then translated into executable PyAutoGUI code.

1. Supported Action Types (action_type)
   hotkey        : Combination keystrokes (e.g., "ctrl v", "ctrl shift s")
   press/keydown : Key held down (uses keyDown)
   release/keyup : Key released (uses keyUp)
   type          : Text input (clipboard paste optimization or direct write)
   click         : Generic left click (alias of left_single)
   left_single   : Left button single click
   left_double   : Left button double click
   right_single  : Right button single click
   hover         : Move mouse without clicking
   drag          : Drag from start_box to end_box
   select        : Alias of drag (semantically a selection gesture)
   scroll        : Scroll wheel at (optional) coordinates
   finished      : Sentinel indicating completion (translated to DONE)

2. Structured Format
Each grounded action becomes:
{
  "reflection": Optional[str],        # High-level self-critique if provided
  "thought": Optional[str],           # Immediate reasoning for the action
  "action_type": str,                 # One of the supported types above
  "action_inputs": {                  # Parameters dependent on action_type
       "start_box": [x1, y1, x2, y2] or [x, y] (stringified list of floats normalized 0-1)
       "end_box":   [x1, y1, x2, y2] (for drag/select)
       "content":   "text to type" (for type)
       "hotkey":    "ctrl v" or "ctrl shift s" (space separated keys)
       "key"/"press": "enter" | "tab" | "arrowdown" | etc.
       "direction": "up" | "down" (for scroll)
  },
  "text": str                         # Original raw model response segment
}

Normalization:
- Bounding boxes are converted to relative coordinates (floats in [0,1]) derived from raw model output.
- If the model returns a single point, it is expanded to a 2-point box [x, y, x, y] for consistency.
- Keys like arrowleft/arrowright/arrowup/arrowdown are canonicalized to left/right/up/down.
- Space key may appear as "space" and is converted to " " for PyAutoGUI.
"""

# Yes we need this shit until polymorphism is allowed in SQLModel
import ast
import asyncio
import math

# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: Apache-2.0
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import List

from fastapi import WebSocketDisconnect
from PIL import Image
from strands import Agent, ToolContext, tool
from strands.models.openai import OpenAIModel

from agent_tools.hooks import AgentLoggingHook
from agent_tools.image import screenshot_bytes
from config import Config
from modules.uierror.prompts import (
    STANDALONE_COMPUTER_USE_DOUBAO,
)
from settings import (
    PROVIDER_API_BASE,
    PROVIDER_API_KEY,
    PROVIDER_GROUNDING_MODEL,
)

IMAGE_FACTOR = 28
MIN_PIXELS = 100 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200


def convert_point_to_coordinates(text, is_answer=False):
    # 匹配 <bbox> 后面的四个数字
    pattern = r"<point>(\d+)\s+(\d+)</point>"

    def replace_match(match):
        x1, y1 = map(int, match.groups())
        x = (x1 + x1) // 2  # 使用截断取整
        y = (y1 + y1) // 2  # 使用截断取整
        if is_answer:
            return f"({x},{y})"  # 只返回 (x, y) 格式
        return f"({x},{y})"  # 返回带标签的格式

    # 去掉 [EOS] 并替换 <bbox> 坐标
    text = re.sub(r"\[EOS\]", "", text)
    return re.sub(pattern, replace_match, text).strip()


# 定义一个函数来解析每个 action
def parse_action(action_str):
    try:
        # 解析字符串为 AST 节点
        node = ast.parse(action_str, mode="eval")

        # 确保节点是一个表达式
        if not isinstance(node, ast.Expression):
            raise ValueError("Not an expression")

        # 获取表达式的主体
        call = node.body

        # 确保主体是一个函数调用
        if not isinstance(call, ast.Call):
            raise ValueError("Not a function call")

        # 获取函数名
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        else:
            func_name = None

        # 获取关键字参数
        kwargs = {}
        for kw in call.keywords:
            key = kw.arg
            # 处理不同类型的值，这里假设都是常量
            if isinstance(kw.value, ast.Constant):
                value = kw.value.value
            elif isinstance(kw.value, ast.Str):  # 兼容旧版本 Python
                value = kw.value.s
            else:
                value = None
            kwargs[key] = value

        return {"function": func_name, "args": kwargs}

    except Exception as e:
        print(f"Failed to parse action '{action_str}': {e}")
        return None


def escape_single_quotes(text):
    # 匹配未转义的单引号（不匹配 \\'）
    pattern = r"(?<!\\)'"
    return re.sub(pattern, r"\\'", text)


def round_by_factor(number: float, factor: int) -> int:
    """Returns the closest integer to 'number' that is divisible by 'factor'."""
    return round(number / factor) * factor


def ceil_by_factor(number: float, factor: int) -> int:
    """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
    return math.ceil(number / factor) * factor


def floor_by_factor(number: float, factor: int) -> int:
    """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
    return math.floor(number / factor) * factor


def linear_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    if width * height > max_pixels:
        """
        如果图片超过/低于像素限制，则计算一个缩放因子resize_factor，使图片的像素数缩小到等于或小于max_pixels。这个缩放因子是通过开平方根计算的，确保纵横比保持不变,这样原始的相对坐标可以不经转换直接复用
        """
        resize_factor = math.sqrt(max_pixels / (width * height))
        width, height = int(width * resize_factor), int(height * resize_factor)
    if width * height < min_pixels:
        resize_factor = math.sqrt(min_pixels / (width * height))
        width, height = (
            math.ceil(width * resize_factor),
            math.ceil(height * resize_factor),
        )

    return height, width


def smart_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    """
    Rescales the image so that the following conditions are met:

    1. Both dimensions (height and width) are divisible by 'factor'.

    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].

    3. The aspect ratio of the image is maintained as closely as possible.
    """
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def parse_action_to_structure_output(
    text,
    origin_resized_height,
    origin_resized_width,
    factor=IMAGE_FACTOR,
    model_type="qwen25vl",
    max_pixels=16384 * 28 * 28,
    min_pixels=100 * 28 * 28,
) -> List[dict]:
    """
    将M模型的输出解析为结构化的action列表
    参数:
        text: 模型输出的字符串
        origin_resized_height: 原始图像的高度
        origin_resized_width: 原始图像的宽度
        factor: 缩放因子
        model_type: 模型类型，决定坐标处理方式
    返回:
        结构化的action列表，每个action是一个字典，包含以下字段:
        - reflection: 反思内容（如果有）
        - thought: 思考内容
        - action_type: 动作类型
        - action_inputs: 动作输入参数
        - text: 原始文本
    """
    text = text.strip()

    if "<point>" in text:
        text = convert_point_to_coordinates(text)
    if "start_point=" in text:
        text = text.replace("start_point=", "start_box=")
    if "end_point=" in text:
        text = text.replace("end_point=", "end_box=")
    if "point=" in text:
        text = text.replace("point=", "start_box=")

    if model_type == "qwen25vl":
        smart_resize_height, smart_resize_width = smart_resize(
            origin_resized_height,
            origin_resized_width,
            factor=IMAGE_FACTOR,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )

    # 正则表达式匹配 Action 字符串
    if text.startswith("Thought:"):
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
    elif text.startswith("Reflection:"):
        thought_pattern = r"Reflection: (.+?)Action_Summary: (.+?)(?=\s*Action: |$)"
    elif text.startswith("Action_Summary:"):
        thought_pattern = r"Action_Summary: (.+?)(?=\s*Action: |$)"
    else:
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
    reflection, thought = None, None
    thought_match = re.search(thought_pattern, text, re.DOTALL)
    if thought_match:
        if len(thought_match.groups()) == 1:
            thought = thought_match.group(1).strip()
        elif len(thought_match.groups()) == 2:
            thought = thought_match.group(2).strip()
            reflection = thought_match.group(1).strip()
    assert "Action:" in text
    action_str = text.split("Action: ")[-1]

    tmp_all_action = action_str.split(")\n\n")
    all_action = []
    for action_str in tmp_all_action:
        if "type(content" in action_str:
            if not action_str.strip().endswith(")"):
                action_str = action_str.strip() + ")"

            # 正则表达式匹配 content 中的字符串并转义单引号
            def escape_quotes(match):
                content = match.group(1)  # 获取 content 的值
                return content

            # 使用正则表达式进行替换
            pattern = r"type\(content='(.*?)'\)"  # 匹配 type(content='...')
            if re.search(pattern, action_str):  # 检查是否有匹配项
                content = re.sub(pattern, escape_quotes, action_str)
            else:
                raise ValueError("Pattern not found in the input string.")

            # 处理字符串
            action_str = escape_single_quotes(content)
            action_str = "type(content='" + action_str + "')"
        if not action_str.strip().endswith(")"):
            action_str = action_str.strip() + ")"
        all_action.append(action_str)

    parsed_actions = [
        parse_action(action.replace("\n", "\\n").lstrip()) for action in all_action
    ]
    actions = []
    for action_instance, raw_str in zip(parsed_actions, all_action):
        if not action_instance:
            print(f"Action can't parse: {raw_str}")
            raise ValueError(f"Action can't parse: {raw_str}")
        action_type = action_instance["function"]
        params = action_instance["args"]
        # Normalization
        if action_type == "press":
            action_type = "keydown"
        elif action_type == "release":
            action_type = "keyup"

        # import pdb; pdb.set_trace()
        action_inputs = {}
        for param_name, param in params.items():
            if param == "":
                continue
            param = param.lstrip()  # 去掉引号和多余的空格
            # 处理start_box或者end_box参数格式 '<bbox>x1 y1 x2 y2</bbox>'
            if action_type == "hotkey" and "key" in param_name:
                param_name = "hotkey"
            if "press" in param_name or "key" in param_name:
                match param:
                    case "arrowleft":
                        param = "left"
                    case "arrowright":
                        param = "right"
                    case "arrowup":
                        param = "up"
                    case "arrowdown":
                        param = "down"
                    case "space":
                        param = " "
                action_inputs["key"] = param  # Normalization

            if "start_box" in param_name or "end_box" in param_name:
                ori_box = param
                # Remove parentheses and split the string by commas
                numbers = ori_box.split("(")[-1].split(")")[0].split(",")

                # Convert to float and scale by 1000
                # Qwen2.5vl output absolute coordinates, qwen2vl output relative coordinates
                if model_type == "qwen25vl":
                    float_numbers = []
                    for num_idx, num in enumerate(numbers):
                        num = float(num)
                        if (num_idx + 1) % 2 == 0:
                            float_numbers.append(float(num / smart_resize_height))  # pyright:ignore[reportPossiblyUnboundVariable]
                        else:
                            float_numbers.append(float(num / smart_resize_width))  # pyright:ignore[reportPossiblyUnboundVariable]
                else:
                    float_numbers = [float(num) / factor for num in numbers]

                if len(float_numbers) == 2:
                    float_numbers = [
                        float_numbers[0],
                        float_numbers[1],
                        float_numbers[0],
                        float_numbers[1],
                    ]
                action_inputs[param_name.strip()] = float_numbers

            else:
                action_inputs[param_name.strip()] = param

        # import pdb; pdb.set_trace()
        actions.append(
            {
                "reflection": reflection,
                "thought": thought,
                "action_type": action_type,
                "action_inputs": action_inputs,
                "text": text,
            }
        )
    return actions


def parsing_response_to_pyautogui_code(
    responses, image_height: int, image_width: int, input_swap: bool = True
) -> str:
    """
    将M模型的输出解析为OSWorld中的action，生成pyautogui代码字符串
    参数:
        response: 包含模型输出的字典，结构类似于：
        {
            "action_type": "hotkey",
            "action_inputs": {
                "hotkey": "v ctrl",
                "start_box": None,
                "end_box": None
            }
        }
    返回:
        生成的pyautogui代码字符串
    """

    pyautogui_code = "import pyautogui\nimport time\n"
    if isinstance(responses, dict):
        responses = [responses]
    for response_id, response in enumerate(responses):
        if "observation" in response:
            observation = response["observation"]
        else:
            observation = ""

        if "thought" in response:
            thought = response["thought"]
        else:
            thought = ""

        if response_id == 0:
            pyautogui_code += (
                f"'''\nObservation:\n{observation}\n\nThought:\n{thought}\n'''\n"
            )
        else:
            pyautogui_code += "\ntime.sleep(1)\n"

        action_dict = response
        action_type = action_dict.get("action_type")
        action_inputs = action_dict.get("action_inputs", {})

        if action_type == "hotkey":
            # Parsing hotkey action
            if "key" in action_inputs:
                hotkey = action_inputs.get("key", "")
            else:
                hotkey = action_inputs.get("hotkey", "")

            if hotkey == "arrowleft":
                hotkey = "left"

            elif hotkey == "arrowright":
                hotkey = "right"

            elif hotkey == "arrowup":
                hotkey = "up"

            elif hotkey == "arrowdown":
                hotkey = "down"

            if hotkey:
                # Handle other hotkeys
                keys = hotkey.split()  # Split the keys by space
                convert_keys = []
                for key in keys:
                    if key == "space":
                        key = " "
                    convert_keys.append(key)
                pyautogui_code += (
                    f"\npyautogui.hotkey({', '.join([repr(k) for k in convert_keys])})"
                )

        elif action_type in ["press", "keydown"]:
            # Parsing press action
            if "key" in action_inputs:
                key_to_press = action_inputs.get("key", "")
            else:
                key_to_press = action_inputs.get("press", "")

            if key_to_press == "arrowleft":
                key_to_press = "left"

            elif key_to_press == "arrowright":
                key_to_press = "right"

            elif key_to_press == "arrowup":
                key_to_press = "up"

            elif key_to_press == "arrowdown":
                key_to_press = "down"

            elif key_to_press == "space":
                key_to_press = " "

            if key_to_press:
                # Simulate pressing a single key
                pyautogui_code += f"\npyautogui.keyDown({repr(key_to_press)})"

        elif action_type in ["release", "keyup"]:
            # Parsing press action
            if "key" in action_inputs:
                key_to_press = action_inputs.get("key", "")
            else:
                key_to_press = action_inputs.get("press", "")

            if key_to_press == "arrowleft":
                key_to_press = "left"

            elif key_to_press == "arrowright":
                key_to_press = "right"

            elif key_to_press == "arrowup":
                key_to_press = "up"

            elif key_to_press == "arrowdown":
                key_to_press = "down"

            elif key_to_press == "space":
                key_to_press = " "

            if key_to_press:
                # Simulate pressing a single key
                pyautogui_code += f"\npyautogui.keyUp({repr(key_to_press)})"

        elif action_type == "type":
            # Parsing typing action using clipboard
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            stripped_content = content
            if content.endswith("\n") or content.endswith("\\n"):
                stripped_content = stripped_content.rstrip("\\n").rstrip("\n")
            if content:
                if input_swap:
                    pyautogui_code += "\nimport pyperclip"
                    pyautogui_code += f"\npyperclip.copy('{stripped_content}')"
                    pyautogui_code += "\npyautogui.hotkey('ctrl', 'v')"
                    pyautogui_code += "\ntime.sleep(0.5)\n"
                    if content.endswith("\n") or content.endswith("\\n"):
                        pyautogui_code += "\npyautogui.press('enter')"
                else:
                    pyautogui_code += (
                        f"\npyautogui.write('{stripped_content}', interval=0.1)"
                    )
                    pyautogui_code += "\ntime.sleep(0.5)\n"
                    if content.endswith("\n") or content.endswith("\\n"):
                        pyautogui_code += "\npyautogui.press('enter')"

        elif action_type in ["drag", "select"]:
            # Parsing drag or select action based on start and end_boxes
            start_box = action_inputs.get("start_box")
            end_box = action_inputs.get("end_box")
            if start_box and end_box:
                x1, y1, x2, y2 = eval(start_box)  # Assuming box is in [x1, y1, x2, y2]
                sx = round(float((x1 + x2) / 2) * image_width, 3)
                sy = round(float((y1 + y2) / 2) * image_height, 3)
                x1, y1, x2, y2 = eval(end_box)  # Assuming box is in [x1, y1, x2, y2]
                ex = round(float((x1 + x2) / 2) * image_width, 3)
                ey = round(float((y1 + y2) / 2) * image_height, 3)
                pyautogui_code += (
                    f"\npyautogui.moveTo({sx}, {sy})\n"
                    f"\npyautogui.dragTo({ex}, {ey}, duration=1.0)\n"
                )

        elif action_type == "scroll":
            # Parsing scroll action
            start_box = action_inputs.get("start_box")
            if start_box:
                x1, y1, x2, y2 = eval(start_box)  # Assuming box is in [x1, y1, x2, y2]
                x = round(float((x1 + x2) / 2) * image_width, 3)
                y = round(float((y1 + y2) / 2) * image_height, 3)

                # # 先点对应区域，再滚动
                # pyautogui_code += f"\npyautogui.click({x}, {y}, button='left')"
            else:
                x = None
                y = None
            direction = action_inputs.get("direction", "")

            if not x:
                if "up" in direction.lower():
                    pyautogui_code += "\npyautogui.scroll(5)"
                elif "down" in direction.lower():
                    pyautogui_code += "\npyautogui.scroll(-5)"
            else:
                if "up" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(5, x={x}, y={y})"
                elif "down" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(-5, x={x}, y={y})"

        elif action_type in [
            "click",
            "left_single",
            "left_double",
            "right_single",
            "hover",
        ]:
            # Parsing mouse click actions
            start_box = action_inputs.get("start_box")
            start_box = str(start_box)
            if start_box:
                start_box = eval(start_box)
                if not isinstance(start_box, List):
                    raise ValueError("start_box is not list of int")
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box  # Assuming box is in [x1, y1, x2, y2]
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2 = x1
                    y2 = y1
                else:
                    raise ValueError("start_box length is not 2 or 4")
                if not (
                    isinstance(x1, (int, float))
                    and isinstance(y1, (int, float))
                    and isinstance(x2, (int, float))
                    and isinstance(y2, (int, float))
                ):
                    raise ValueError("start_box coordinates are not numbers")
                x = round(float((x1 + x2) / 2) * image_width, 3)
                y = round(float((y1 + y2) / 2) * image_height, 3)
                if action_type == "left_single" or action_type == "click":
                    pyautogui_code += f"\npyautogui.click({x}, {y}, button='left')"
                elif action_type == "left_double":
                    pyautogui_code += (
                        f"\npyautogui.doubleClick({x}, {y}, button='left')"
                    )
                elif action_type == "right_single":
                    pyautogui_code += f"\npyautogui.click({x}, {y}, button='right')"
                elif action_type == "hover":
                    pyautogui_code += f"\npyautogui.moveTo({x}, {y})"

        elif action_type in ["finished"]:
            pyautogui_code = "DONE"

        else:
            pyautogui_code += f"\n# Unrecognized action type: {action_type}"

    return pyautogui_code


def add_box_token(input_string):
    # Step 1: Split the string into individual actions
    if "Action: " in input_string and "start_box=" in input_string:
        suffix = input_string.split("Action: ")[0] + "Action: "
        actions = input_string.split("Action: ")[1:]
        processed_actions = []
        for action in actions:
            action = action.strip()
            # Step 2: Extract coordinates (start_box or end_box) using regex
            coordinates = re.findall(
                r"(start_box|end_box)='\((\d+),\s*(\d+)\)'", action
            )

            updated_action = action  # Start with the original action
            for coord_type, x, y in coordinates:
                # Convert x and y to integers
                updated_action = updated_action.replace(
                    f"{coord_type}='({x},{y})'",
                    f"{coord_type}='<|box_start|>({x},{y})<|box_end|>'",
                )
            processed_actions.append(updated_action)

        # Step 5: Reconstruct the final string
        final_string = suffix + "\n\n".join(processed_actions)
    else:
        final_string = input_string
    return final_string


@tool(
    name="standalone_uitars",
    description="A element and action ground model for UI tasks.",
    context=True,
)
async def standalone_uitars(
    task: str,
    action_history: list,
    failed_activity: dict,
    variables: dict,
    tool_context: ToolContext,
) -> list:
    """
    This function is to be called by the ui_exception_handler tool to execute a recovery plan for a UI error.

    Args:
        task (str): The task description that the robot was trying to complete
        action_history (list): The history of actions taken by the robot (list)
        failed_activity (dict): The action that was expected to be performed but failed (dict)
        variables (dict): A dictionary of variables used in the process

    Returns:
        Dictionary containing status and tool response:
        {
            "toolUseId": "unique_id",
            "status": "success|error",
            "content": [{"text": "Recovery plan or error message"}]
        }

        Success: Returns a textual recovery plan or JSON-serializable plan in content[0]["text"].
        Error: Returns information about what went wrong.
    """
    # conversation_history = [
    #     """Thought: I'm currently looking at the login page of the interface. The username has already been entered, and we're just one step away from completing the login process. There's a purple "Continue" button located just below the username section right in front of me. After I finish entering the username, I need to click this button to proceed to the next step.
    #     Action: type(content='PassWord')""",
    #     """Thought: It seems that the password field hasn't fully loaded yet, and my previous attempt to enter the password didn't go through. Right now, I'm facing this login screen with a purple "Welcome Back" text at the top. The username section already has "admin" filled in, but the password section still appears blank. I need to click on the password input box again to make sure it successfully captures my input this time.
    #     Action: click(start_box='(784,622)')""",
    #     """Thought: I noticed that the username has already been entered. Now, I'll need to click on the password field again to make sure it becomes active, so I can proceed with the password entry process
    #     Action: click(start_box='(834,662)')""",
    #     """Thought: It appears that my previous click on the text box didn't successfully activate the input field. However, that's alright; the username is already filled in. Now, all I need to do is re-click on the password field, and that should allow me to start entering the password. Let's go ahead and complete this step.
    #     Action: click(start_box='(850,655)')""",
    #     """Thought: I glanced at the screen and saw the login page displaying \"Welcome Back.\" The username field was already filled with "admin." This time, I really needed to make sure that the input field was properly activated, as it would allow me to get ready for entering the password in the next step.
    #     Action: click(start_box='(884,670)')""",
    #     """Thought: It seems that my previous attempts haven’t had any effect, so it looks like I need to change my approach. On the screen, there’s a prominent purple login box that says "Welcome Back." I’ve already filled in the username, and now I need to click the purple "Continue" button below to proceed to the next step.
    #     Action: click(start_box='(938,765)')""",
    #     """Thought: I see that there is a password input box currently awaiting my entry. The task clearly specifies that the password is "admin." I'll click on the input box first, and then I can go ahead and type in the password.
    #     Action: click(start_box='(873,701)')""",
    #     """Thought: The setup process is progressing well; the username has been chosen, and the password field is right in front of me. The task instructions clearly state that I need to enter "admin" in the password section, so I'll go ahead and input that password now. Once I finish typing it in, we can move on to the next step of the login verification process.
    #     Action: type(content='admin')""",
    #     """Thought: Alright, the username and password have all been set up perfectly. Now there’s just one final step left – I can see a prominent purple "Sign In" button at the bottom of the login screen, right underneath the Back button. I need to click this button to complete the entire login process.
    #     Action: click(start_box='(1031,797)')""",
    #     """Thought: After patiently seeing the \"Welcome back, admin\" message and all the system status displays, it's clear that the login process has been successfully completed. The system has fully validates the username "admin" and the password we entered, allowing us to access all features and secure the session. Since the login verification has been successfully achieved, this entire authentication workflow has now come to a successful conclusion.
    #     Action: finished(content='登录成功了，现在可以开始体验系统的全部功能了。')""",
    # ]
    # return conversation_history

    instruction = f"""
Task: {task}
Action History: {action_history}
Failed Action: {failed_activity}
Variables: {variables}
"""

    assert "websocket" in tool_context.invocation_state, (
        "WebSocket must be provided in tool context"
    )
    websocket = tool_context.invocation_state["websocket"]
    image = await screenshot_bytes(websocket)
    image_size = Image.open(BytesIO(image)).size

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": STANDALONE_COMPUTER_USE_DOUBAO.format(
                        instruction=instruction
                    )
                },
                {
                    "type": "image",
                    "image": {
                        "format": "jpeg",
                        "source": {"bytes": image},
                    },
                },
            ],
        },
    ]

    model = OpenAIModel(
        client_args={"api_key": PROVIDER_API_KEY, "base_url": PROVIDER_API_BASE},
        model_id=PROVIDER_GROUNDING_MODEL,
    )

    hook = AgentLoggingHook(
        agent_id=uuid.UUID("d3befb44-ade2-479d-b71c-b76fa0bddc1c"),  # Huge mega hack
        invocation_state=tool_context.invocation_state,
        parent_trace_id=tool_context.invocation_state.get("parent_trace_id", None),
        is_gui_agent=True,
    )
    agent = Agent(model=model, messages=messages, hooks=[hook])  # type: ignore

    try:
        response = await agent.invoke_async(
            ""
        )  # Empty input since all context is in messages
        _ = response.metrics.accumulated_usage.get("inputTokens", 0)
        _ = response.metrics.accumulated_usage.get("outputTokens", 0)

        iteration = 0

        while True:
            iteration += 1
            if iteration > Config.MAX_ACTIONS_ALLOWED:
                return [{"text": "Exceeded maximum allowed actions."}]

            ui_tars_response = ""
            try:
                ui_tars_response = response.message.get("content", "")[0].get(
                    "text", ""
                )
            except Exception:
                ui_tars_response = str(response)
                break

            try:
                action = parse_action_to_structure_output(
                    ui_tars_response,
                    origin_resized_height=image_size[1],
                    origin_resized_width=image_size[0],
                )[0]
                code = parsing_response_to_pyautogui_code(
                    action, image_size[1], image_size[0]
                )

                if code == "DONE":
                    await hook.register_gui_trace(
                        action_type=action.get("action_type", "unknown"),
                        action_content=action.get("action_inputs", {}),
                        screenshot_bytes=image,
                        success=True,
                        started_at=datetime.now(),
                        finished_at=datetime.now(),
                    )
                    break

                start_datetime = datetime.now()
                await websocket.send_json(
                    {"type": "action", "content": action}
                )  # Action will be parsed and executed by the client
                # Wait for action result
                result = await websocket.receive_json()
                finish_datetime = datetime.now()
                if not result.get("success"):
                    await hook.register_gui_trace(
                        action_type=action.get("action_type", "unknown"),
                        action_content=action.get("action_inputs", {}),
                        screenshot_bytes=image,
                        success=False,
                        started_at=start_datetime,
                        finished_at=finish_datetime,
                    )
                    raise RuntimeError(
                        f"Action execution failed on client side. With action: {action}"
                    )

                await hook.register_gui_trace(
                    action_type=action.get("action_type", "unknown"),
                    action_content=action.get("action_inputs", {}),
                    screenshot_bytes=image,
                    success=True,
                    started_at=start_datetime,
                    finished_at=finish_datetime,
                )

                # Artificial delay to allow UI to update
                await asyncio.sleep(0.5)
                image = await screenshot_bytes(websocket)
                image_size = Image.open(BytesIO(image)).size

                new_messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "image": {
                                    "format": "jpeg",
                                    "source": {"bytes": image},
                                },
                            },
                        ],
                    },
                ]

                response = await agent.invoke_async(
                    new_messages  # type: ignore
                )
                _ = response.metrics.accumulated_usage.get("inputTokens", 0)
                _ = response.metrics.accumulated_usage.get("outputTokens", 0)
            except WebSocketDisconnect as _:
                raise
            except RuntimeError as _:
                raise
            except Exception as _:
                response = agent("The action failed. Try again")
                continue

        conversation_history = list(
            map(
                lambda m: m["content"],
                filter(lambda m: m["role"] == "assistant", agent.messages),
            )
        )
        return conversation_history

    except WebSocketDisconnect as _:
        raise
    except RuntimeError as _:
        raise
    except Exception as e:
        return [{"text": str(e)}]
    finally:
        cost = -1.0
        hook.update_trace(finished=True, cost=cost)
