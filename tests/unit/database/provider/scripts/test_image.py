import pytest

from database.provider.scripts.image import Qwen2_5ImageResizer


def test_smart_resize_rounds_square_images_to_factor():
    assert Qwen2_5ImageResizer.smart_resize(1000, 1000) == (1008, 1008)


def test_smart_resize_pads_small_images():
    assert Qwen2_5ImageResizer.smart_resize(100, 100) == (280, 280)


def test_smart_resize_downscales_large_images():
    assert Qwen2_5ImageResizer.smart_resize(4000, 4000) == (3584, 3584)


def test_smart_resize_preserves_aspect_ratio():
    assert Qwen2_5ImageResizer.smart_resize(1080, 1920) == (1092, 1932)


def test_smart_resize_rejects_extreme_aspect_ratio():
    with pytest.raises(ValueError, match="aspect ratio"):
        Qwen2_5ImageResizer.smart_resize(10, 3000)


def test_smart_resize_rejects_non_positive_dimensions():
    with pytest.raises(ValueError, match="positive"):
        Qwen2_5ImageResizer.smart_resize(0, 100)
