import pytest


@pytest.fixture(autouse=True)
def mock_s3client_model(monkeypatch):  # pyright: ignore[reportMissingParameterType]
    import database.logging.models as logging_models_mod
    import routers.logging as logging_router
    import s3 as s3_mod
    from s3 import utils as s3_utils
    from tests.unit.shared import mock_s3
    from tests.unit.shared.mock_s3 import MockS3Client

    mock_s3.clear_store()

    monkeypatch.setattr(s3_utils, "S3Client", MockS3Client, raising=True)
    monkeypatch.setattr(s3_mod, "S3Client", MockS3Client, raising=True)
    monkeypatch.setattr(logging_models_mod, "S3Client", MockS3Client, raising=True)
    monkeypatch.setattr(logging_router, "S3Client", MockS3Client, raising=True)

    return {
        "s3_utils": s3_utils,
        "s3_mod": s3_mod,
        "logging_models_mod": logging_models_mod,
        "logging_router": logging_router,
    }
