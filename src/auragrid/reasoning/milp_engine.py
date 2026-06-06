import logging
import pulp
from typing import Dict, List, Tuple
from auragrid.config import settings
from auragrid.models.grid_state import GridState
from auragrid.grid.topology import GridTopology, EdgeTopology
from auragrid.models.agent_action import MitigationPlan, AgentAction, ActionType
from auragrid.reasoning.base_engine import BaseReasoningEngine
from auragrid.perception.forecaster_stub import get_forecast

logger = logging.getLogger("auragrid.milp_engine")

class MILPEngine(BaseReasoningEngine):
    def decide(self, state: GridState, topology: GridTopology) -> MitigationPlan:
        """
        Solves the Mixed-Integer Linear Program (MILP) over a receding horizon.
        Formulation from SPEC-AG-001 Section 3.
        """
        H = settings.horizon_steps
        nodes = list(topology.nodes.keys())
        edges = topology.edges
        
        # Get forecast for future steps (k = 2 to H)
        forecast = get_forecast(state, steps_ahead=H-1)
        
        # Build load and generation profiles for each node at each step k (1-indexed)
        # k = 1 is the current state
        load_profile: Dict[str, List[float]] = {}
        gen_profile: Dict[str, List[float]] = {}
        
        for node_name in nodes:
            load_profile[node_name] = [0.0] * (H + 1)
            gen_profile[node_name] = [0.0] * (H + 1)
            
            # Current state (k = 1)
            current_node = state.nodes.get(node_name)
            if current_node:
                load_profile[node_name][1] = current_node.active_load_mw
                gen_profile[node_name][1] = current_node.generation_mw
            else:
                # Fallback to topology
                node_topo = topology.nodes[node_name]
                load_profile[node_name][1] = node_topo.base_load_mw
                gen_profile[node_name][1] = node_topo.generation_mw
                
            # Forecast states (k = 2 to H)
            for idx, step in enumerate(forecast.steps):
                k = idx + 2
                if k <= H:
                    load_profile[node_name][k] = step.predicted_load_mw.get(node_name, load_profile[node_name][1])
                    # Generation assumed constant or matches telemetry
                    gen_profile[node_name][k] = gen_profile[node_name][1]

        # Initialize the optimization problem
        prob = pulp.LpProblem("AuraGrid_MPC_Mitigation", pulp.LpMinimize)
        
        # --- Variables ---
        # delta_P[i][k]: Load shedded at node i at step k (continuous)
        delta_P = {}
        for i in nodes:
            delta_P[i] = {}
            for k in range(1, H + 1):
                max_shed = load_profile[i][k]
                delta_P[i][k] = pulp.LpVariable(
                    f"delta_P_{i.replace(' ', '_')}_{k}",
                    lowBound=0.0,
                    upBound=max_shed,
                    cat=pulp.LpContinuous
                )
                
        # u[e][k]: Binary state of transmission line e at step k (binary)
        u = {}
        for idx, e in enumerate(edges):
            u[idx] = {}
            for k in range(1, H + 1):
                u[idx][k] = pulp.LpVariable(
                    f"u_{idx}_{k}",
                    cat=pulp.LpBinary
                )
                
        # s[idx][k]: Aux variable for absolute change |u_e(k) - u_e(k-1)| (continuous)
        s = {}
        for idx, e in enumerate(edges):
            s[idx] = {}
            for k in range(1, H + 1):
                s[idx][k] = pulp.LpVariable(
                    f"s_{idx}_{k}",
                    lowBound=0.0,
                    cat=pulp.LpContinuous
                )
                
        # P_flow[idx][k]: Power flow on line e at step k (continuous)
        P_flow = {}
        for idx, e in enumerate(edges):
            P_flow[idx] = {}
            for k in range(1, H + 1):
                P_flow[idx][k] = pulp.LpVariable(
                    f"P_flow_{idx}_{k}",
                    cat=pulp.LpContinuous
                )

        # --- Objective Function ---
        # Sum_{k=1}^H ( Sum_i W_shed * delta_P_i(k) + Sum_e W_switch * s_e(k) )
        obj_terms = []
        for k in range(1, H + 1):
            for i in nodes:
                # Add higher penalty for critical nodes
                node_topo = topology.nodes.get(i)
                w_shed = settings.shed_penalty
                if node_topo and node_topo.is_critical_infrastructure:
                    w_shed *= 100.0  # 100x penalty for critical infrastructure
                obj_terms.append(w_shed * delta_P[i][k])
                
            for idx, e in enumerate(edges):
                obj_terms.append(settings.switch_penalty * s[idx][k])
                
        prob += pulp.lpSum(obj_terms)

        # --- Constraints ---
        # 1. Initial line states (k=0) to compute wear and tear at k=1
        initial_u = {}
        for idx, e in enumerate(edges):
            # Check breaker state from telemetry or use topology default
            # We look at both endpoints of the edge or specific breaker state in state.nodes if available.
            # But edges represent transmission lines, so we default to 1 (Closed) unless telemetry tells us otherwise.
            initial_u[idx] = 1.0

        for k in range(1, H + 1):
            # 2. Node Power Balance (Kirchhoff's Current Law) for each node i
            for i in nodes:
                incoming_flow = []
                outgoing_flow = []
                for idx, e in enumerate(edges):
                    if e.to_node == i:
                        incoming_flow.append(P_flow[idx][k])
                    elif e.from_node == i:
                        outgoing_flow.append(P_flow[idx][k])
                
                # KCL: sum(In) - sum(Out) + Gen - (Load - delta_P) = 0
                prob += (
                    pulp.lpSum(incoming_flow) - pulp.lpSum(outgoing_flow) + 
                    gen_profile[i][k] - (load_profile[i][k] - delta_P[i][k]) == 0,
                    f"KCL_{i.replace(' ', '_')}_{k}"
                )
                
            # 3. Line Thermal Capacity (Ohm's Law constraints)
            # -u_e(k) * S_max <= P_flow_e(k) <= u_e(k) * S_max
            for idx, e in enumerate(edges):
                limit = e.thermal_limit_mw
                prob += (P_flow[idx][k] <= u[idx][k] * limit, f"Thermal_Limit_Pos_{idx}_{k}")
                prob += (P_flow[idx][k] >= -u[idx][k] * limit, f"Thermal_Limit_Neg_{idx}_{k}")
                
            # 4. Switch Wear-and-Tear Linearization:
            # s_e(k) >= u_e(k) - u_e(k-1)
            # s_e(k) >= u_e(k-1) - u_e(k)
            for idx, e in enumerate(edges):
                prev_u = u[idx][k-1] if k > 1 else initial_u[idx]
                prob += (s[idx][k] >= u[idx][k] - prev_u, f"Switch_Linear_A_{idx}_{k}")
                prob += (s[idx][k] >= prev_u - u[idx][k], f"Switch_Linear_B_{idx}_{k}")

        # Solve the MILP
        solver = pulp.PULP_CBC_CMD(msg=False)
        try:
            status = prob.solve(solver)
        except Exception as ex:
            logger.error(f"Solver failed: {ex}")
            status = pulp.LpStatusInfeasible

        actions: List[AgentAction] = []
        obj_val = None
        
        if status == pulp.LpStatusOptimal:
            obj_val = pulp.value(prob.objective)
            # Extract immediate decisions (k = 1)
            for i in nodes:
                shed_val = pulp.value(delta_P[i][1])
                if shed_val is not None and shed_val > 0.05:  # threshold to ignore float noise
                    load_val = load_profile[i][1]
                    percent = (shed_val / max(load_val, 1.0)) * 100.0
                    actions.append(AgentAction(
                        action_type=ActionType.SHED_LOAD,
                        target_node=i,
                        parameters={
                            "shed_percentage": round(percent, 2),
                            "shed_mw": round(shed_val, 2)
                        }
                    ))
                    
            for idx, e in enumerate(edges):
                u_val = pulp.value(u[idx][1])
                prev_u_val = initial_u[idx]
                if u_val is not None and round(u_val) == 0 and prev_u_val == 1:
                    # Line should be opened. We target the to_node for isolation
                    actions.append(AgentAction(
                        action_type=ActionType.ISOLATE_NODE,
                        target_node=e.to_node,
                        parameters={
                            "reason": "Preventive cascade isolation",
                            "line_from": e.from_node,
                            "line_to": e.to_node,
                            "breaker_id": e.breaker_id
                        }
                    ))
        else:
            logger.warning("MILP Solver could not find an optimal solution. Reverting to safe default.")
            
        return MitigationPlan(
            agent_id="AuraGrid-Mitigator-MILP",
            actions=actions,
            solver_objective_value=obj_val,
            guardrail_status="PENDING",
            rejection_reasons=[]
        )
