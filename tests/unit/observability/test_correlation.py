from fastapi import FastAPI
from fastapi.testclient import TestClient

from observability.correlation import RequestContextMiddleware, get_request_id


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/echo")
    def echo() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    return app


def test_generates_request_id() -> None:
    response = TestClient(_app()).get("/echo")
    request_id = response.json()["request_id"]

    assert request_id
    assert response.headers["x-request-id"] == request_id


def test_reuses_inbound_request_id() -> None:
    response = TestClient(_app()).get("/echo", headers={"X-Request-ID": "abc-123"})

    assert response.json()["request_id"] == "abc-123"
    assert response.headers["x-request-id"] == "abc-123"


def test_context_is_cleared_after_request() -> None:
    TestClient(_app()).get("/echo")
    assert get_request_id() is None
