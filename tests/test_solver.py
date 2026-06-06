import pytest
from auragrid.reasoning.milp_engine import MILPEngine
from auragrid.models.grid_state import GridState, NodeState
from auragrid.models.agent_action import ActionType

def test_solver_no_action_needed(sample_topology, stable_grid_state):
    """If load < capacity and no risk exists, the solver should do nothing."""
    engine = MILPEngine()
    plan = engine.decide(stable_grid_state, sample_topology)
    
    assert len(plan.actions) == 0

def test_solver_overload_mitigation(sample_topology, stable_grid_state):
    """If load exceeds capacity, the solver should shed load to restore balance."""
    # Overload Node A (base load 400, capacity 800) -> make it 900
    state = stable_grid_state.model_copy(deep=True)
    state.nodes["Node A"].active_load_mw = 900.0
    
    engine = MILPEngine()
    plan = engine.decide(state, sample_topology)
    
    # Check that the solver sheds load on Node A
    shed_actions = [a for a in plan.actions if a.action_type == ActionType.SHED_LOAD]
    assert len(shed_actions) > 0
    assert any(a.target_node == "Node A" for a in shed_actions)
