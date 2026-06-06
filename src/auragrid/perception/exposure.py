from auragrid.models.grid_state import GridState

def calculate_exposure(state: GridState) -> float:
    """
    Calculates the maximum cascade exposure coefficient from the risk matrix.
    Returns a value between 0.0 and 1.0.
    """
    max_risk = 0.0
    for node_from, targets in state.cascade_risk_matrix.items():
        for node_to, risk in targets.items():
            # Risk can be represented as 0.785 or 78.5
            norm_risk = risk / 100.0 if risk > 1.0 else risk
            if norm_risk > max_risk:
                max_risk = norm_risk
    return max_risk

def should_trigger_reasoning(state: GridState, threshold: float = 0.65) -> bool:
    """
    Returns True if the maximum cascade risk exceeds the threshold.
    """
    exposure = calculate_exposure(state)
    return exposure > threshold
