from collections.abc import Callable

from sqlmodel import Session

from database.provider.models import Router


def test_router_defaults_to_text_capability(make_router: Callable[..., Router]):
    router = make_router()

    assert router.capabilities == [Router.Capability.TEXT]


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
