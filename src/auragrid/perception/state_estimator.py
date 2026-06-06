from datetime import datetime
from typing import Optional
from auragrid.models.grid_state import GridState, NodeState
from auragrid.grid.topology import GridTopology, load_grid_topology

class StateEstimator:
    def __init__(self):
        self._current_state: Optional[GridState] = None
        self._topology_cache: dict[str, GridTopology] = {}

    def get_topology(self, city: str) -> GridTopology:
        """Retrieves or loads the topology for a given city."""
        if city not in self._topology_cache:
            self._topology_cache[city] = load_grid_topology(city)
        return self._topology_cache[city]

    def ingest_telemetry(self, state: GridState) -> GridState:
        """
        Ingests the telemetry state. Updates nodes in the topology
        with telemetry values (load, capacity, breaker states).
        """
        # Load topology to ensure all nodes exist and are registered
        topo = self.get_topology(state.active_city)
        
        # Merge telemetry nodes into our full topology node set to handle partial telemetry payloads
        merged_nodes = {}
        for node_name, node_topo in topo.nodes.items():
            if node_name in state.nodes:
                # Use telemetry state
                telemetry_node = state.nodes[node_name]
                merged_nodes[node_name] = NodeState(
                    active_load_mw=telemetry_node.active_load_mw,
                    max_capacity_mw=telemetry_node.max_capacity_mw,
                    generation_mw=telemetry_node.generation_mw if telemetry_node.generation_mw > 0 else node_topo.generation_mw,
                    status=telemetry_node.status,
                    breaker_state=telemetry_node.breaker_state
                )
            else:
                # Use default topology state
                merged_nodes[node_name] = NodeState(
                    active_load_mw=node_topo.base_load_mw,
                    max_capacity_mw=node_topo.max_capacity_mw,
                    generation_mw=node_topo.generation_mw,
                    status="NORMAL",
                    breaker_state="CLOSED"
                )

        # Update node status based on load ratios
        for name, node in merged_nodes.items():
            if node.breaker_state == "OPEN":
                node.status = "ISOLATED"
            else:
                ratio = node.active_load_mw / max(node.max_capacity_mw, 1.0)
                if ratio > 0.95:
                    node.status = "CRITICAL_CASCADE_RISK"
                elif ratio > 0.80:
                    node.status = "VULNERABLE"
                else:
                    node.status = "NORMAL"

        self._current_state = GridState(
            timestamp=state.timestamp,
            active_city=state.active_city,
            grid_frequency_hz=state.grid_frequency_hz,
            nodes=merged_nodes,
            cascade_risk_matrix=state.cascade_risk_matrix
        )
        return self._current_state

    def get_current_state(self, default_city: str = "BESCOM_Bengaluru_Grid") -> GridState:
        """Returns the current estimated grid state."""
        if self._current_state is None:
            # Generate a default initial state from the topology
            topo = self.get_topology(default_city)
            nodes = {
                name: NodeState(
                    active_load_mw=node.base_load_mw,
                    max_capacity_mw=node.max_capacity_mw,
                    generation_mw=node.generation_mw,
                    status="NORMAL",
                    breaker_state="CLOSED"
                )
                for name, node in topo.nodes.items()
            }
            self._current_state = GridState(
                timestamp=datetime.utcnow(),
                active_city=default_city,
                grid_frequency_hz=50.0,
                nodes=nodes,
                cascade_risk_matrix={}
            )
        return self._current_state

# Singleton instance of StateEstimator
state_estimator = StateEstimator()
