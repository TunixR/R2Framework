import os

import dotenv

# Load environment variables from .env file
_ = dotenv.load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "gateway")
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")

POSTGRES_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

PROVIDER = os.getenv("PROVIDER", "")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")
FREE_PROVIDER_API_KEY = os.getenv("FREE_PROVIDER_API_KEY", "")
PROVIDER_API_BASE = os.getenv("PROVIDER_API_BASE", "")
PROVIDER_MODEL = os.getenv("PROVIDER_MODEL", "")
PROVIDER_VISION_MODEL = os.getenv("PROVIDER_VISION_MODEL", "")
PROVIDER_VISION_TOOL_MODEL = os.getenv("PROVIDER_VISION_TOOL_MODEL", "")
PROVIDER_GROUNDING_MODEL = os.getenv("PROVIDER_GROUNDING_MODEL", "")
PROVIDER_GROUNDING_MODEL_BACKBONE = os.getenv("PROVIDER_GROUNDING_MODEL_BACKBONE", "")
MAX_GUI_IMAGES = int(os.getenv("MAX_GUI_IMAGES", "5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

UI_ERROR_PLANNING = os.getenv("UI_ERROR_PLANNING", "false").lower() == "true"
UI_MID_AGENT = os.getenv("UI_MID_AGENT", "false").lower() == "true"

S3_URL = os.getenv("S3_URL", "http://localhost:8333")
S3_BUCKET = os.getenv("S3_BUCKET", "gateway")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "your_access_key")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "your_secret_key")

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
ALGORITHM = os.getenv("ALGORITHM", "HS256")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Observability (traces and logs exported over OTLP to SigNoz)
OBSERVABILITY_ENABLED = (
    os.getenv("OBSERVABILITY_ENABLED", "true").lower() == "true"
    and os.getenv("OTEL_SDK_DISABLED", "false").lower() != "true"
)
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "r2framework-api")
OTEL_SERVICE_NAMESPACE = os.getenv("OTEL_SERVICE_NAMESPACE", "r2framework")
DEPLOYMENT_ENVIRONMENT = os.getenv("DEPLOYMENT_ENVIRONMENT", "development")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
)
OTEL_TRACES_SAMPLER_ARG = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json").lower()
LOG_FILE = os.getenv("LOG_FILE") or None
LOG_FILE_MAX_BYTES = int(os.getenv("LOG_FILE_MAX_BYTES", "10000000"))
LOG_FILE_BACKUP_COUNT = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))
STRANDS_LOG_LEVEL = os.getenv("STRANDS_LOG_LEVEL", "INFO").upper()
# Longest free text (task names, process models...) put on spans and events.
TELEMETRY_MAX_TEXT_LENGTH = int(os.getenv("TELEMETRY_MAX_TEXT_LENGTH", "120"))

# SigNoz access for tests/integration/observability (not used by the app)
SIGNOZ_CLICKHOUSE_URL = os.getenv("SIGNOZ_CLICKHOUSE_URL") or None
SIGNOZ_CLICKHOUSE_CONTAINER = os.getenv(
    "SIGNOZ_CLICKHOUSE_CONTAINER", "signoz-clickhouse"
)
SIGNOZ_POLL_TIMEOUT = float(os.getenv("SIGNOZ_POLL_TIMEOUT", "60"))
