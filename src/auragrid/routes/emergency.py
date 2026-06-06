from fastapi import APIRouter, Depends
from auragrid.auth import verify_agent_token
from auragrid.failsafe.emergency_disconnect import emergency_disconnect
from auragrid.failsafe.watchdog import watchdog

router = APIRouter()

@router.post("/emergency/disconnect")
def post_disconnect():
    """
    Activates the Emergency Disconnect Switch (E-stop).
    Does not require authentication to allow instant operator intervention.
    """
    emergency_disconnect.activate()
    return {
        "status": "DISCONNECTED",
        "message": "Emergency disconnect activated. SCADA channels immediately severed."
    }

@router.post("/emergency/reconnect")
def post_reconnect(token: str = Depends(verify_agent_token)):
    """
    Deactivates the Emergency Disconnect Switch.
    Requires secure agent token to reconnect.
    """
    emergency_disconnect.deactivate()
    return {
        "status": "RECONNECTED",
        "message": "Emergency disconnect deactivated. SCADA channels restored."
    }

@router.post("/watchdog/fail")
def post_watchdog_fail():
    """
    Simulates a communication failure where the agent stops receiving pings/ACKs.
    Useful for testing watchdog write access revocation.
    """
    watchdog.simulate_communication_failure = True
    return {
        "status": "COMMUNICATION_FAILURE_SIMULATED",
        "message": "Watchdog now simulating communication failure. Access will revoke in 30 seconds."
    }

@router.post("/watchdog/restore")
def post_watchdog_restore():
    """
    Restores normal communication for the watchdog.
    """
    watchdog.simulate_communication_failure = False
    return {
        "status": "COMMUNICATION_RESTORED",
        "message": "Watchdog restored. Access will be re-granted on the next successful heartbeat ping."
    }
