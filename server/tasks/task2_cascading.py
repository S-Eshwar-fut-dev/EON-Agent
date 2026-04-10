from server.models import IncidentState, IncidentAction
from typing import List

def grade(state: IncidentState, action_history: List[IncidentAction]) -> float:
    steps = state.steps_taken
    root = state.root_cause_service
    resolved = state.resolved
    
    fixed_root = False
    fixed_downstream = False
    
    for act in action_history:
        if act.action in ["apply_fix", "rollback"]:
            if act.target_service == root:
                fixed_root = True
            elif act.target_service:
                fixed_downstream = True

    if resolved:
        if not fixed_downstream and steps <= 10:
            return 0.95
        else:
            return 0.62
    elif fixed_downstream and not fixed_root:
        return 0.28
    else:
        return 0.05
