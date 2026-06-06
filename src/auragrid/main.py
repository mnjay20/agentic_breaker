import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auragrid.failsafe.watchdog import watchdog
from auragrid.routes import mitigate, telemetry, health, emergency

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("auragrid.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown events."""
    logger.info("Initializing AuraGrid automated core...")
    # Start the watchdog keep-alive ping loop
    await watchdog.start()
    yield
    # Stop the watchdog keep-alive ping loop on shutdown
    await watchdog.stop()
    logger.info("AuraGrid automated core shutdown complete.")

app = FastAPI(
    title="AuraGrid Mitigation Core API",
    description="Deterministic closed-loop control, MILP decision optimization, and physics guardrails.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for potential operator web console access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes under /api/v1 prefix
app.include_router(mitigate.router, prefix="/api/v1")
app.include_router(telemetry.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(emergency.router, prefix="/api/v1")

@app.get("/")
def get_root():
    return {
        "system": "AuraGrid Automated Load Switching & Node Isolation Core",
        "api_documentation": "/docs"
    }
