import re
from datetime import datetime
from auragrid.models.agent_action import MitigationPlan, ActionType
from auragrid.models.scada_command import ExecutionSequence, DeviceCommand
from auragrid.grid.topology import GridTopology

def clean_device_id(name: str) -> str:
    """Helper to format node names into device IDs."""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', name).upper()
    return re.sub(r'_+', '_', clean).strip('_')

class CommandTranslator:
    def translate(self, plan: MitigationPlan, topology: GridTopology) -> ExecutionSequence:
        """
        Translates a high-level MitigationPlan into a detailed SCADA ExecutionSequence
        containing discrete device commands.
        """
        device_commands = []
        step_counter = 1

        # Phase 1: Load shedding commands (do first to stabilize system)
        for action in plan.actions:
            if action.action_type == ActionType.SHED_LOAD:
                node_name = action.target_node
                shed_mw = action.parameters.get("shed_mw", 0.0)
                device_id = f"LS_{clean_device_id(node_name)}"
                
                device_commands.append(DeviceCommand(
                    step=step_counter,
                    device_type="LOAD_SHEDGER",
                    device_id=device_id,
                    target_state="ACTIVE",
                    interlock_bypass=False,
                    shed_limit_mw=round(shed_mw, 2)
                ))
                step_counter += 1

        # Phase 2: Breaker switching / Node isolation commands
        for action in plan.actions:
            if action.action_type == ActionType.ISOLATE_NODE:
                node_name = action.target_node
                
                # Find all lines (edges) connected to this node in the topology
                for edge in topology.edges:
                    if edge.from_node == node_name or edge.to_node == node_name:
                        device_commands.append(DeviceCommand(
                            step=step_counter,
                            device_type="BREAKER",
                            device_id=edge.breaker_id,
                            target_state="OPEN",
                            interlock_bypass=False
                        ))
                        step_counter += 1

        return ExecutionSequence(
            timestamp_utc=datetime.utcnow(),
            execution_sequence=device_commands
        )
