from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    SHED_LOAD = "SHED_LOAD"
    SHIFT_LOAD = "SHIFT_LOAD"
    ISOLATE_NODE = "ISOLATE_NODE"

class AgentAction(BaseModel):
    action_type: ActionType
    target_node: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class MitigationPlan(BaseModel):
    agent_id: str = "AuraGrid-Mitigator-MILP"
    actions: List[AgentAction] = Field(default_factory=list)
    solver_objective_value: Optional[float] = None
    guardrail_status: Optional[str] = "PENDING"
    rejection_reasons: Optional[List[str]] = None
