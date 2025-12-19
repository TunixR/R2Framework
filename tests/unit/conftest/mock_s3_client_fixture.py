import pytest


@pytest.fixture(autouse=False, scope="function")
def fake_s3client_model(monkeypatch):
    from s3 import utils as s3_utils
    from tests.unit.shared.mock_s3 import MockS3Client

    monkeypatch.setattr(s3_utils, "S3Client", MockS3Client, raising=True)
