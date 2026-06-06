import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from auragrid.auth import verify_agent_token
from auragrid.config import settings
from auragrid.failsafe.watchdog import watchdog
from auragrid.failsafe.emergency_disconnect import emergency_disconnect
from auragrid.models.scada_command import ExecutionSequence, SCADAMitigateResponse, SCADAVerification
from auragrid.models.agent_action import MitigationPlan, AgentAction, ActionType
from auragrid.perception.state_estimator import state_estimator
from auragrid.reasoning.milp_engine import MILPEngine
from auragrid.guardrails.physics_guardrail import PhysicsGuardrail
from auragrid.guardrails.safety_checks import run_safety_checks
from auragrid.actuation.command_translator import CommandTranslator
from auragrid.actuation.scada_client_stub import SCADAClientStub

logger = logging.getLogger("auragrid.routes.mitigate")
router = APIRouter(prefix="/agent")

# Guard check helper
def check_safety_locks():
    """Verifies emergency disconnect and watchdog access limits."""
    if emergency_disconnect.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCADA Actuation Blocked: Emergency Disconnect switch is active."
        )
    
    watchdog_status = watchdog.get_status()
    if not watchdog_status["write_access_granted"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"SCADA Actuation Blocked: Watchdog timer timeout (last ACK was {watchdog_status['seconds_since_last_ack']}s ago)."
        )

def map_sequence_to_plan(sequence: ExecutionSequence, state_city: str) -> MitigationPlan:
    """
    Reverse-translates a SCADA ExecutionSequence back into a high-level MitigationPlan
    so the guardrail layer can evaluate it.
    """
    topo = state_estimator.get_topology(state_city)
    state = state_estimator.get_current_state(state_city)
    
    actions = []
    
    for cmd in sequence.execution_sequence:
        if cmd.device_type == "LOAD_SHEDGER" and cmd.target_state == "ACTIVE":
            target_node = None
            for node_name in topo.nodes.keys():
                clean_name = cmd.device_id.replace("LS_", "").replace("_", " ").lower()
                if clean_name in node_name.lower():
                    target_node = node_name
                    break
            
            if not target_node:
                target_node = list(topo.nodes.keys())[0]
                
            node_state = state.nodes.get(target_node)
            active_load = node_state.active_load_mw if node_state else 100.0
            limit = cmd.shed_limit_mw or 0.0
            
            pct = (limit / max(active_load, 1.0)) * 100.0
            actions.append(AgentAction(
                action_type=ActionType.SHED_LOAD,
                target_node=target_node,
                parameters={"shed_percentage": min(100.0, pct), "shed_mw": limit}
            ))
            
        elif cmd.device_type == "BREAKER" and cmd.target_state == "OPEN":
            target_node = None
            for edge in topo.edges:
                if edge.breaker_id == cmd.device_id:
                    target_node = edge.to_node
                    break
                    
            if not target_node:
                parts = cmd.device_id.split("_")
                if len(parts) >= 3:
                    target_node = parts[2].replace("_", " ")
                else:
                    target_node = list(topo.nodes.keys())[0]
                    
            actions.append(AgentAction(
                action_type=ActionType.ISOLATE_NODE,
                target_node=target_node,
                parameters={"breaker_id": cmd.device_id, "reason": "Explicit breaker open command"}
            ))
            
    return MitigationPlan(
        agent_id="AuraGrid-External-Agent",
        actions=actions
    )

@router.post("/mitigate", response_model=SCADAMitigateResponse)
def post_mitigate(
    sequence: ExecutionSequence,
    token: str = Depends(verify_agent_token)
):
    """
    REST Endpoint (SPEC-AG-001 §5) to allow the agent to issue commands.
    Validates the proposed command sequence against the Physics Guardrail Layer
    and Safety Checks before dispatching to SCADA.
    """
    check_safety_locks()
    
    current_state = state_estimator.get_current_state()
    topology = state_estimator.get_topology(current_state.active_city)
    
    plan = map_sequence_to_plan(sequence, current_state.active_city)
    
    safety_result = run_safety_checks(plan, current_state, topology)
    if not safety_result.approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Safety checks rejected the command sequence.",
                "reasons": safety_result.reasons
            }
        )
        
    pgl = PhysicsGuardrail()
    pgl_result = pgl.validate(plan, current_state, topology)
    if not pgl_result.approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Physics Guardrail Layer rejected the command sequence.",
                "reasons": pgl_result.rejection_reasons
            }
        )
        
    scada_client = SCADAClientStub()
    response = scada_client.dispatch(
        sequence, 
        estimated_freq_impact=pgl_result.estimated_frequency_impact_hz
    )
    
    return response

@router.post("/solve")
def post_solve(
    dispatch: bool = False,
    token: str = Depends(verify_agent_token)
):
    """
    Autonomous solve endpoint. Runs the MILP optimization model
    to generate an optimal mitigation plan, validates it via guardrails,
    and optionally dispatches it to SCADA.
    """
    if dispatch:
        check_safety_locks()
        
    current_state = state_estimator.get_current_state()
    topology = state_estimator.get_topology(current_state.active_city)
    
    # 1. Run MILP optimization
    engine = MILPEngine()
    plan = engine.decide(current_state, topology)
    
    if not plan.actions:
        return {
            "status": "NO_ACTION_REQUIRED",
            "message": "Grid is stable. No load shedding or node isolation needed.",
            "plan": plan
        }
        
    # 2. Run safety checks
    safety_result = run_safety_checks(plan, current_state, topology)
    plan.guardrail_status = "APPROVED" if safety_result.approved else "REJECTED"
    if not safety_result.approved:
        plan.rejection_reasons = safety_result.reasons
        return {
            "status": "REJECTED_BY_SAFETY_CHECKS",
            "plan": plan
        }
        
    # 3. Run physics guardrail validation
    pgl = PhysicsGuardrail()
    pgl_result = pgl.validate(plan, current_state, topology)
    plan.guardrail_status = "APPROVED" if pgl_result.approved else "REJECTED"
    if not pgl_result.approved:
        plan.rejection_reasons = pgl_result.rejection_reasons
        return {
            "status": "REJECTED_BY_PHYSICS_GUARDRAIL",
            "plan": plan
        }
        
    # 4. Translate plan to SCADA execution sequence
    translator = CommandTranslator()
    sequence = translator.translate(plan, topology)
    
    # 5. Optionally dispatch
    scada_response = None
    if dispatch:
        scada_client = SCADAClientStub()
        scada_response = scada_client.dispatch(
            sequence, 
            estimated_freq_impact=pgl_result.estimated_frequency_impact_hz
        )
        
    return {
        "status": "SOLVED_AND_APPROVED",
        "plan": plan,
        "execution_sequence": sequence,
        "scada_dispatch_response": scada_response
    }
