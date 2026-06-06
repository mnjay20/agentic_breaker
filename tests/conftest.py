import os
import sys
import pytest
from datetime import datetime

# Add src to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from auragrid.models.grid_state import GridState, NodeState
from auragrid.grid.topology import GridTopology, NodeTopology, EdgeTopology

@pytest.fixture
def sample_topology() -> GridTopology:
    """Provides a basic 4-node topology for testing."""
    nodes = {
        "Node A": NodeTopology(
            name="Node A", voltage_kv=220.0, is_critical_infrastructure=False,
            max_capacity_mw=800.0, base_load_mw=400.0, generation_mw=0.0, taluk="Taluk 1"
        ),
        "Node B": NodeTopology(
            name="Node B", voltage_kv=220.0, is_critical_infrastructure=True,  # Hospital node
            max_capacity_mw=800.0, base_load_mw=300.0, generation_mw=0.0, taluk="Taluk 1"
        ),
        "Node C": NodeTopology(
            name="Node C", voltage_kv=400.0, is_critical_infrastructure=False,
            max_capacity_mw=1500.0, base_load_mw=100.0, generation_mw=900.0, taluk="Taluk 2" # Gen Node
        ),
        "Node D": NodeTopology(
            name="Node D", voltage_kv=66.0, is_critical_infrastructure=False,
            max_capacity_mw=200.0, base_load_mw=100.0, generation_mw=0.0, taluk="Taluk 2"
        ),
    }
    
    edges = [
        EdgeTopology(from_node="Node C", to_node="Node A", thermal_limit_mw=600.0, breaker_id="CB_C_A"),
        EdgeTopology(from_node="Node C", to_node="Node B", thermal_limit_mw=600.0, breaker_id="CB_C_B"),
        EdgeTopology(from_node="Node A", to_node="Node D", thermal_limit_mw=150.0, breaker_id="CB_A_D"),
    ]
    
    adj = {
        "Node A": ["Node C", "Node D"],
        "Node B": ["Node C"],
        "Node C": ["Node A", "Node B"],
        "Node D": ["Node A"],
    }
    
    return GridTopology(
        city="TestCity",
        nodes=nodes,
        edges=edges,
        adjacency_list=adj
    )

@pytest.fixture
def stable_grid_state() -> GridState:
    """Provides a stable, normal-load grid state matching the sample topology."""
    return GridState(
        timestamp=datetime.utcnow(),
        active_city="TestCity",
        grid_frequency_hz=50.0,
        nodes={
            "Node A": NodeState(active_load_mw=400.0, max_capacity_mw=800.0, status="NORMAL", breaker_state="CLOSED"),
            "Node B": NodeState(active_load_mw=300.0, max_capacity_mw=800.0, status="NORMAL", breaker_state="CLOSED"),
            "Node C": NodeState(active_load_mw=100.0, max_capacity_mw=1500.0, generation_mw=900.0, status="NORMAL", breaker_state="CLOSED"),
            "Node D": NodeState(active_load_mw=100.0, max_capacity_mw=200.0, status="NORMAL", breaker_state="CLOSED"),
        },
        cascade_risk_matrix={}
    )
