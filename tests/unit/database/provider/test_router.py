from collections.abc import Callable

import pytest
from sqlmodel import Session

from database.provider.models import Router


def test_router_defaults_to_text_capability(make_router: Callable[..., Router]):
    router = make_router()

    assert router.capabilities == [Router.Capability.TEXT]


def test_router_defaults_vision_backbone_to_none_without_vision(
    make_router: Callable[..., Router],
):
    router = make_router()

    assert router.vision_backbone is None


def test_router_defaults_vision_backbone_to_other_with_vision(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )

    assert router.vision_backbone == Router.VisionBackbone.OTHER


def test_router_clears_vision_backbone_without_vision(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT],
        vision_backbone=Router.VisionBackbone.QWEN3_5,
    )

    assert router.vision_backbone is None


def test_router_supports_configured_capabilities(
    make_router: Callable[..., Router],
):
    text_router = make_router()
    vision_router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )

    assert text_router.supports_capabilities(Router.Capability.TEXT)
    assert not text_router.supports_capabilities(Router.Capability.VISION)
    assert vision_router.supports_capabilities(Router.Capability.TEXT)
    assert vision_router.supports_capabilities(Router.Capability.VISION)


def test_router_capabilities_persist_as_json(
    session: Session, make_router: Callable[..., Router]
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )

    persisted = session.get(Router, router.id)

    assert persisted is not None
    assert [Router.Capability(capability) for capability in persisted.capabilities] == [
        Router.Capability.TEXT,
        Router.Capability.VISION,
    ]


def test_router_vision_backbone_persists(
    session: Session, make_router: Callable[..., Router]
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION],
        vision_backbone=Router.VisionBackbone.QWEN2_5,
    )
    session.expire_all()

    persisted = session.get(Router, router.id)

    assert persisted is not None
    assert persisted.vision_backbone == Router.VisionBackbone.QWEN2_5


##############################
# -- Vision coordinate space
##############################


def test_router_relative_dim_is_identity_for_other_backbone(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )

    assert router.relative_dim(1080, 1920) == [1080, 1920]
    assert router.original_coords(540, 960, 1920, 1080) == [540, 960]


def test_router_relative_dim_is_identity_for_qwen38(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION],
        vision_backbone=Router.VisionBackbone.QWEN3_8,
    )

    assert router.relative_dim(1080, 1920) == [1080, 1920]
    assert router.original_coords(540, 960, 1920, 1080) == [540, 960]


def test_router_relative_dim_uses_1000_square_for_qwen35(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION],
        vision_backbone=Router.VisionBackbone.QWEN3_5,
    )

    assert router.relative_dim(500, 1000) == [1000, 1000]
    assert router.original_coords(500, 250, 500, 1000) == [250, 250]


def test_router_relative_dim_smart_resizes_for_qwen25(
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION],
        vision_backbone=Router.VisionBackbone.QWEN2_5,
    )

    assert router.relative_dim(1000, 1000) == [1008, 1008]
    assert router.original_coords(504, 504, 1000, 1000) == [500, 500]


def test_router_relative_dim_rejects_non_positive_dimensions(
    make_router: Callable[..., Router],
):
    router = make_router()

    with pytest.raises(ValueError, match="positive"):
        router.relative_dim(0, 100)
