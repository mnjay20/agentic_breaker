import numpy as np
import logging
from typing import Dict, List, Tuple
from pydantic import BaseModel
from auragrid.config import settings
from auragrid.models.grid_state import GridState
from auragrid.grid.topology import GridTopology
from auragrid.models.agent_action import MitigationPlan, ActionType

logger = logging.getLogger("auragrid.physics_guardrail")

class GuardrailResult(BaseModel):
    approved: bool
    rejection_reasons: List[str]
    estimated_frequency_impact_hz: float
    estimated_rof_hz_s: float

def solve_dc_power_flow(
    nodes: List[str], 
    edges: List[Tuple[str, str, float]], 
    loads: Dict[str, float], 
    gens: Dict[str, float]
) -> Tuple[Dict[str, float], bool]:
    """
    Solves linear DC power flow for a given grid configuration.
    Returns a dict mapping line index/tuple to power flow in MW, and a success boolean.
    
    DC Power Flow equations:
    P_injection_i = Sum_j B_ij * (theta_i - theta_j)
    For each transmission line (i, j), we assume reactance X_ij = 1.0 (so B_ij = 1 / X_ij = 1.0).
    """
    num_nodes = len(nodes)
    if num_nodes <= 1:
        return {}, True

    node_to_idx = {name: idx for idx, name in enumerate(nodes)}
    
    # Construct susceptance matrix B
    B_mat = np.zeros((num_nodes, num_nodes))
    for u, v, _ in edges:
        if u in node_to_idx and v in node_to_idx:
            i, j = node_to_idx[u], node_to_idx[v]
            B_mat[i, i] += 1.0
            B_mat[j, j] += 1.0
            B_mat[i, j] -= 1.0
            B_mat[j, i] -= 1.0

    # Net injections: P_gen - P_load
    P_inject = np.array([gens.get(name, 0.0) - loads.get(name, 0.0) for name in nodes])
    
    # If total generation != total load, adjust slightly to keep system balanced (slack bus adjustment)
    total_inject = np.sum(P_inject)
    if abs(total_inject) > 1e-3:
        # Distribute the slack among all online generator nodes
        gen_nodes = [name for name in nodes if gens.get(name, 0.0) > 0.0]
        if gen_nodes:
            adj = total_inject / len(gen_nodes)
            for name in gen_nodes:
                idx = node_to_idx[name]
                P_inject[idx] -= adj
        else:
            # Distribute among all nodes
            P_inject -= total_inject / num_nodes
            
    # Set node 0 as reference/slack bus (theta_0 = 0)
    # Solve (B_mat[:-1, :-1]) * theta[:-1] = P_inject[:-1]
    theta = np.zeros(num_nodes)
    if num_nodes > 1:
        B_sub = B_mat[:-1, :-1]
        P_sub = P_inject[:-1]
        try:
            # Solve using least-squares to handle isolated/singular subgraphs gracefully
            theta_sub, _, _, _ = np.linalg.lstsq(B_sub, P_sub, rcond=None)
            theta[:-1] = theta_sub
        except Exception as ex:
            logger.error(f"Power flow solver failed: {ex}")
            return {}, False

    # Calculate flows
    flows = {}
    for u, v, limit in edges:
        if u in node_to_idx and v in node_to_idx:
            i, j = node_to_idx[u], node_to_idx[v]
            # Susceptance B_ij = 1.0
            flow = (theta[i] - theta[j])
            flows[(u, v)] = flow
            
    return flows, True


class PhysicsGuardrail:
    def validate(self, plan: MitigationPlan, state: GridState, topology: GridTopology) -> GuardrailResult:
        """
        Runs the Physics Guardrail Layer validation checks on the proposed MitigationPlan.
        """
        rejection_reasons = []
        
        # 1. Identify proposed actions
        isolated_nodes = set()
        shed_amounts = {}
        for action in plan.actions:
            if action.action_type == ActionType.ISOLATE_NODE:
                isolated_nodes.add(action.target_node)
            elif action.action_type == ActionType.SHED_LOAD:
                pct = action.parameters.get("shed_percentage", 0.0)
                shed_amounts[action.target_node] = pct

        # 2. Compute dynamic frequency deviation (df/dt - RoCoF)
        # Spec §1: evaluate df/dt before dropping node to prevent total collapse
        total_online_load = sum(node.active_load_mw for node in state.nodes.values() if node.breaker_state == "CLOSED")
        total_online_capacity = sum(node.max_capacity_mw for node in state.nodes.values() if node.breaker_state == "CLOSED")
        
        delta_P_imbalance = 0.0  # Net load shed (+) or generation lost (-)
        
        for name, node in state.nodes.items():
            if name in isolated_nodes:
                # Isolating a node removes its load (frequency rises +) and generation (frequency falls -)
                delta_P_imbalance += (node.active_load_mw - node.generation_mw)
            elif name in shed_amounts:
                # Shedding load reduces load (frequency rises +)
                shed_mw = node.active_load_mw * (shed_amounts[name] / 100.0)
                delta_P_imbalance += shed_mw
                
        # Swing Equation: df/dt = (f_0 * delta_P) / (2 * H_sys * P_sys)
        f_0 = state.grid_frequency_hz
        H_sys = settings.system_inertia
        P_sys = max(total_online_capacity, 100.0)
        
        # RoCoF (Rate of Change of Frequency) in Hz/s
        rof = (f_0 * delta_P_imbalance) / (2 * H_sys * P_sys)
        estimated_frequency_impact = rof * 1.0  # 1-second impact
        
        # Threshold: if |RoCoF| > 0.5 Hz/s, reject
        if abs(rof) > 0.5:
            rejection_reasons.append(
                f"Rate of Change of Frequency (RoCoF) limit breached: {rof:.3f} Hz/s (limit is ±0.5 Hz/s)"
            )

        # 3. KCL and Thermal Overload checks via DC Power Flow simulation
        # Determine remaining nodes & edges after isolation
        remaining_nodes = [name for name in topology.nodes.keys() if name not in isolated_nodes]
        remaining_edges = []
        for edge in topology.edges:
            if edge.from_node not in isolated_nodes and edge.to_node not in isolated_nodes:
                remaining_edges.append((edge.from_node, edge.to_node, edge.thermal_limit_mw))
                
        # Compute new loads and gens
        new_loads = {}
        new_gens = {}
        for name in remaining_nodes:
            node_state = state.nodes.get(name)
            base_load = node_state.active_load_mw if node_state else topology.nodes[name].base_load_mw
            base_gen = node_state.generation_mw if node_state else topology.nodes[name].generation_mw
            
            # Apply load shedding
            shed_pct = shed_amounts.get(name, 0.0)
            new_loads[name] = base_load * (1.0 - shed_pct / 100.0)
            new_gens[name] = base_gen

        # Solve DC Power Flow
        flows, pf_success = solve_dc_power_flow(remaining_nodes, remaining_edges, new_loads, new_gens)
        
        if not pf_success:
            rejection_reasons.append("DC Power Flow simulation failed to converge.")
        else:
            # Check thermal limits
            for (u, v), flow in flows.items():
                # Find line limit from remaining edges
                limit = 100.0
                for edge_from, edge_to, edge_limit in remaining_edges:
                    if (edge_from == u and edge_to == v) or (edge_from == v and edge_to == u):
                        limit = edge_limit
                        break
                        
                if abs(flow) > limit:
                    rejection_reasons.append(
                        f"Thermal overload on line ({u} -> {v}): simulated flow {abs(flow):.1f} MW exceeds capacity {limit:.1f} MW"
                    )

        # 4. Islanding / Isolation checks
        # Verify that no nodes are left isolated without any source of power unless explicitly isolated
        for name in remaining_nodes:
            # If a node has load but no connection and no local generation, it has suffered a blackout
            has_generation = new_gens.get(name, 0.0) > 0
            is_connected = False
            for u, v, _ in remaining_edges:
                if u == name or v == name:
                    is_connected = True
                    break
            if not is_connected and not has_generation and new_loads.get(name, 0.0) > 5.0:
                rejection_reasons.append(
                    f"Action creates islanded node '{name}' without local generation or line connections (Blackout risk)"
                )

        approved = len(rejection_reasons) == 0
        return GuardrailResult(
            approved=approved,
            rejection_reasons=rejection_reasons,
            estimated_frequency_impact_hz=round(estimated_frequency_impact, 3),
            estimated_rof_hz_s=round(rof, 3)
        )
