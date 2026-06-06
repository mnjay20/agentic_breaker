import logging
from typing import Dict, List
from auragrid.config import settings
from auragrid.models.grid_state import GridState
from auragrid.grid.topology import GridTopology
from auragrid.models.agent_action import MitigationPlan, ActionType

logger = logging.getLogger("auragrid.safety_checks")

class SafetyCheckResult:
    def __init__(self, approved: bool, reasons: List[str] = None):
        self.approved = approved
        self.reasons = reasons or []

def run_safety_checks(plan: MitigationPlan, state: GridState, topology: GridTopology) -> SafetyCheckResult:
    """
    Applies safety rules described in SPEC-AG-001 Section 4:
    1. Critical Infrastructure protection (Hospitals, Emergency services)
    2. Total shedded load limits (Max 30% load shed of partition)
    """
    reasons = []

    # 1. Critical Infrastructure protection
    for action in plan.actions:
        node_name = action.target_node
        node_topo = topology.nodes.get(node_name)
        if node_topo and node_topo.is_critical_infrastructure:
            if action.action_type == ActionType.ISOLATE_NODE:
                reasons.append(
                    f"Forbidden action: Cannot isolate node '{node_name}' as it contains hospital or emergency services."
                )
            elif action.action_type == ActionType.SHED_LOAD:
                shed_pct = action.parameters.get("shed_percentage", 0.0)
                if shed_pct > 50.0:
                    reasons.append(
                        f"Forbidden action: Shed percentage {shed_pct}% on critical infrastructure node '{node_name}' exceeds 50.0% safety limit."
                    )

    # 2. Total shedded load limits (30% max limit)
    total_active_load = 0.0
    total_shed_load = 0.0

    for name, node in state.nodes.items():
        if node.breaker_state == "CLOSED":
            total_active_load += node.active_load_mw

    for action in plan.actions:
        if action.action_type == ActionType.SHED_LOAD:
            node_name = action.target_node
            node_state = state.nodes.get(node_name)
            if node_state and node_state.breaker_state == "CLOSED":
                pct = action.parameters.get("shed_percentage", 0.0)
                total_shed_load += node_state.active_load_mw * (pct / 100.0)

    if total_active_load > 0.0:
        shed_fraction = total_shed_load / total_active_load
        if shed_fraction > settings.max_shed_fraction:
            reasons.append(
                f"Shed limit exceeded: Total shedded load ({total_shed_load:.1f} MW) represents {shed_fraction*100:.1f}% "
                f"of active partition load, exceeding the maximum allowed limit of {settings.max_shed_fraction*100:.1f}%."
            )

    approved = len(reasons) == 0
    return SafetyCheckResult(approved=approved, reasons=reasons)
