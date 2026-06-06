import pytest
from auragrid.models.agent_action import MitigationPlan, AgentAction, ActionType
from auragrid.guardrails.physics_guardrail import PhysicsGuardrail
from auragrid.guardrails.safety_checks import run_safety_checks

def test_hospital_isolation_safety_lock(sample_topology, stable_grid_state):
    """Cannot isolate Node B since it has is_critical_infrastructure=True."""
    # Attempt to isolate Node B
    plan = MitigationPlan(
        agent_id="test-agent",
        actions=[
            AgentAction(action_type=ActionType.ISOLATE_NODE, target_node="Node B")
        ]
    )
    
    result = run_safety_checks(plan, stable_grid_state, sample_topology)
    assert not result.approved
    assert any("Cannot isolate node" in reason for reason in result.reasons)

def test_30_percent_partition_shed_lock(sample_topology, stable_grid_state):
    """Cannot shed more than 30% of total active partition load."""
    # Total active load = 400 + 300 + 100 + 100 = 900 MW.
    # 30% is 270 MW.
    # Attempt to shed 350 MW from Node A
    plan = MitigationPlan(
        agent_id="test-agent",
        actions=[
            AgentAction(
                action_type=ActionType.SHED_LOAD,
                target_node="Node A",
                parameters={"shed_percentage": 87.5, "shed_mw": 350.0}
            )
        ]
    )
    
    result = run_safety_checks(plan, stable_grid_state, sample_topology)
    assert not result.approved
    assert any("Shed limit exceeded" in reason for reason in result.reasons)

def test_rof_frequency_guardrail(sample_topology, stable_grid_state):
    """Large immediate change in load should trigger a frequency collapse (df/dt > 0.5) rejection."""
    # Isolate Node A which drops 400 MW.
    # Total capacity = 800+800+1500+200 = 3300.
    # Swing Equation: df/dt = (50 * 400) / (2 * 5 * 3300) = 20000 / 33000 = 0.606 Hz/s (> 0.5 Hz/s)
    plan = MitigationPlan(
        agent_id="test-agent",
        actions=[
            AgentAction(action_type=ActionType.ISOLATE_NODE, target_node="Node A")
        ]
    )
    
    pgl = PhysicsGuardrail()
    result = pgl.validate(plan, stable_grid_state, sample_topology)
    
    print("REJECTIONS:", result.rejection_reasons)
    assert not result.approved
    assert any("RoCoF" in reason for reason in result.rejection_reasons)
    assert result.estimated_rof_hz_s > 0.5
