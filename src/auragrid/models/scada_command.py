from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class DeviceCommand(BaseModel):
    step: int
    device_type: Literal["BREAKER", "LOAD_SHEDGER"]
    device_id: str
    target_state: str  # OPEN/CLOSED for BREAKER, ACTIVE/INACTIVE for LOAD_SHEDGER
    interlock_bypass: bool = False
    shed_limit_mw: Optional[float] = None

class ExecutionSequence(BaseModel):
    timestamp_utc: datetime = Field(default_factory=datetime.utcnow)
    execution_sequence: List[DeviceCommand]

class SCADAVerification(BaseModel):
    interlocks_checked: bool = True
    physics_valid: bool = True
    estimated_frequency_impact_hz: float = 0.0

class SCADAMitigateResponse(BaseModel):
    status: str = "COMMANDS_DISPATCHED"
    transaction_id: str
    verification: SCADAVerification
