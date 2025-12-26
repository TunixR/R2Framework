# Initializes the FastAPI application and includes the main entry point.
# It also sets up the database connection and includes the necessary routers.
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from strands.telemetry import StrandsTelemetry

import database.general as database
from routers.logging import router as logging_router
from routers.recovery import router as recovery_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler to initialize and clean up the database connection.
    """
    strands_telemetry = StrandsTelemetry()
    strands_telemetry.setup_otlp_exporter()  # Send traces to OTLP endpoint
    strands_telemetry.setup_meter(
        enable_console_exporter=False, enable_otlp_exporter=True
    )  # Setup new meter provider and sets it as global

    logging.getLogger("strands").setLevel(logging.DEBUG)
    logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        filename="strands.log",
        filemode="a",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    await database.populate_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(logging_router)
app.include_router(recovery_router)


@app.get("/scalar", include_in_schema=False)
async def root():
    return get_scalar_api_reference(
        # Your OpenAPI document
        openapi_url=app.openapi_url,
        # Avoid CORS issues (optional)
        scalar_proxy_url="https://proxy.scalar.com",
    )
