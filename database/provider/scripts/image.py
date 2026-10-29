"""Image preprocessing helpers for vision backbones."""

import math


class Qwen2_5ImageResizer:
    """Resize image dimensions the way Qwen2.5-VL preprocesses them.

    Both dimensions are padded to a multiple of `IMAGE_FACTOR` pixels while the
    total pixel count stays within [`MIN_PIXELS`, `MAX_PIXELS`], preserving the
    aspect ratio as closely as possible.
    """

    IMAGE_FACTOR = 28
    MIN_PIXELS = 100 * 28 * 28
    MAX_PIXELS = 16384 * 28 * 28
    MAX_RATIO = 200

    @classmethod
    def smart_resize(cls, height: int, width: int) -> tuple[int, int]:
        """Return the dimensions Qwen2.5-VL resizes the image to."""
        if height <= 0 or width <= 0:
            raise ValueError("Image dimensions must be positive.")
        if max(height, width) / min(height, width) > cls.MAX_RATIO:
            raise ValueError(
                "absolute aspect ratio must be smaller than \
                {cls.MAX_RATIO}, got {max(height, width) / min(height, width)}"
            )

        h_bar = max(cls.IMAGE_FACTOR, _round_by_factor(height, cls.IMAGE_FACTOR))
        w_bar = max(cls.IMAGE_FACTOR, _round_by_factor(width, cls.IMAGE_FACTOR))
        if h_bar * w_bar > cls.MAX_PIXELS:
            beta = math.sqrt((height * width) / cls.MAX_PIXELS)
            h_bar = _floor_by_factor(height / beta, cls.IMAGE_FACTOR)
            w_bar = _floor_by_factor(width / beta, cls.IMAGE_FACTOR)
        elif h_bar * w_bar < cls.MIN_PIXELS:
            beta = math.sqrt(cls.MIN_PIXELS / (height * width))
            h_bar = _ceil_by_factor(height * beta, cls.IMAGE_FACTOR)
            w_bar = _ceil_by_factor(width * beta, cls.IMAGE_FACTOR)
        return h_bar, w_bar


def _round_by_factor(number: float, factor: int) -> int:
    """Return the closest integer to ``number`` that is divisible by ``factor``."""
    return round(number / factor) * factor


def _ceil_by_factor(number: float, factor: int) -> int:
    """Return the smallest integer >= ``number`` divisible by ``factor``."""
    return math.ceil(number / factor) * factor


def _floor_by_factor(number: float, factor: int) -> int:
    """Return the largest integer <= ``number`` divisible by ``factor``."""
    return math.floor(number / factor) * factor
