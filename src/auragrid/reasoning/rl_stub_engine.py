from auragrid.models.grid_state import GridState
from auragrid.grid.topology import GridTopology
from auragrid.models.agent_action import MitigationPlan
from auragrid.reasoning.base_engine import BaseReasoningEngine

class RLStubEngine(BaseReasoningEngine):
    def decide(self, state: GridState, topology: GridTopology) -> MitigationPlan:
        """
        Placeholder for trained Reinforcement Learning (PPO) or LLM Agentic Controller.
        Currently raises NotImplementedError as standard format relies on MILPEngine.
        """
        raise NotImplementedError(
            "Agentic Reinforcement Learning (PPO) and LLM Reasoning Engine is currently a placeholder. "
            "Please configure the system to use the standard MILPEngine decision path."
        )
