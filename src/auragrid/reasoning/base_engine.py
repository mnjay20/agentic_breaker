from abc import ABC, abstractmethod
from auragrid.models.grid_state import GridState
from auragrid.grid.topology import GridTopology
from auragrid.models.agent_action import MitigationPlan

class BaseReasoningEngine(ABC):
    @abstractmethod
    def decide(self, state: GridState, topology: GridTopology) -> MitigationPlan:
        """
        Given the current estimated grid state and topology,
        runs optimization/heuristics to return a mitigation action plan.
        """
        pass
