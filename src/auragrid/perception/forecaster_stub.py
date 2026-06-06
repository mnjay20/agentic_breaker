from datetime import datetime, timedelta
from typing import Dict, List
from pydantic import BaseModel
from auragrid.models.grid_state import GridState

class ForecastStep(BaseModel):
    timestamp: datetime
    predicted_load_mw: Dict[str, float]
    cascade_risk_matrix: Dict[str, Dict[str, float]]

class ForecastResult(BaseModel):
    steps: List[ForecastStep]

def get_forecast(state: GridState, steps_ahead: int = 8, step_duration_min: int = 30) -> ForecastResult:
    """
    Stub for the Neuro-Evolutionary Wavelet Forecaster.
    Generates a mock 12-hour look-ahead vector.
    """
    forecast_steps = []
    current_time = state.timestamp
    
    for k in range(1, steps_ahead + 1):
        step_time = current_time + timedelta(minutes=step_duration_min * k)
        
        # Slightly vary loads (e.g. increase load towards peak hours)
        predicted_load = {}
        for name, node in state.nodes.items():
            multiplier = 1.0 + 0.05 * k  # simple growth
            predicted_load[name] = node.active_load_mw * multiplier
            
        # Mock risk matrix: cascade risk grows as load grows
        risk_matrix = {}
        for src, targets in state.cascade_risk_matrix.items():
            risk_matrix[src] = {}
            for dest, base_risk in targets.items():
                risk_matrix[src][dest] = min(100.0, base_risk * (1.0 + 0.08 * k))
                
        forecast_steps.append(ForecastStep(
            timestamp=step_time,
            predicted_load_mw=predicted_load,
            cascade_risk_matrix=risk_matrix
        ))
        
    return ForecastResult(steps=forecast_steps)
