from datetime import datetime
from typing import Dict, Literal
from pydantic import BaseModel, Field

class NodeState(BaseModel):
    active_load_mw: float = Field(..., description="Active load at the node in MW")
    max_capacity_mw: float = Field(..., description="Max capacity of the node in MW")
    generation_mw: float = Field(0.0, description="Active power generation at the node in MW")
    status: Literal["NORMAL", "VULNERABLE", "CRITICAL_CASCADE_RISK", "ISOLATED"] = "NORMAL"
    breaker_state: Literal["CLOSED", "OPEN"] = "CLOSED"

class GridState(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    active_city: str = Field(..., description="City or grid identifier")
    grid_frequency_hz: float = Field(50.0, description="Measured grid frequency in Hz")
    nodes: Dict[str, NodeState] = Field(..., description="Map of node names to their states")
    cascade_risk_matrix: Dict[str, Dict[str, float]] = Field(
        default_factory=dict, 
        description="Propagation risk matrix (values in percentage, e.g. 78.5)"
    )
