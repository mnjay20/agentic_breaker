import time
from fastapi import APIRouter
from auragrid.failsafe.watchdog import watchdog
from auragrid.failsafe.emergency_disconnect import emergency_disconnect
from auragrid.perception.state_estimator import state_estimator
from auragrid.perception.exposure import calculate_exposure

router = APIRouter(prefix="/health")

@router.get("")
def get_health():
    """
    Returns system status, fail-safe parameters, and current grid exposure.
    Used by operators in the Web Control Room.
    """
    current_state = state_estimator.get_current_state()
    exposure = calculate_exposure(current_state)
    watchdog_status = watchdog.get_status()
    
    return {
        "status": "HEALTHY" if watchdog_status["write_access_granted"] and not emergency_disconnect.is_active else "DEGRADED",
        "emergency_disconnect_active": emergency_disconnect.is_active,
        "watchdog": watchdog_status,
        "grid": {
            "active_city": current_state.active_city,
            "grid_frequency_hz": current_state.grid_frequency_hz,
            "exposure_percentage": round(exposure * 100, 2),
            "node_count": len(current_state.nodes)
        },
        "system_time": time.time()
    }
