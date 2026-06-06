import logging
from fastapi import APIRouter, HTTPException, status
from auragrid.models.grid_state import GridState
from auragrid.perception.state_estimator import state_estimator
from auragrid.perception.exposure import calculate_exposure, should_trigger_reasoning
from auragrid.config import settings

logger = logging.getLogger("auragrid.routes.telemetry")
router = APIRouter(prefix="/telemetry")

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def post_telemetry(state: GridState):
    """
    Placeholder endpoint for SCADA telemetry ingestion (SPEC-AG-001 §4).
    Accepts the grid state representation every 30 seconds and feeds it
    into the State Estimator.
    """
    try:
        updated_state = state_estimator.ingest_telemetry(state)
        exposure = calculate_exposure(updated_state)
        triggered = should_trigger_reasoning(updated_state, settings.cascade_risk_threshold)
        
        logger.info(
            f"Telemetry ingested for {updated_state.active_city} at {updated_state.timestamp}. "
            f"Frequency: {updated_state.grid_frequency_hz} Hz. Exposure: {exposure*100:.1f}%. "
            f"Triggered Reasoning: {triggered} (Threshold: {settings.cascade_risk_threshold*100:.1f}%)"
        )
        
        return {
            "status": "INGESTED",
            "active_city": updated_state.active_city,
            "grid_frequency_hz": updated_state.grid_frequency_hz,
            "exposure_percentage": round(exposure * 100, 2),
            "reasoning_triggered": triggered
        }
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf)
        )
    except Exception as ex:
        logger.error(f"Failed to ingest telemetry: {ex}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telemetry ingestion failed: {str(ex)}"
        )
