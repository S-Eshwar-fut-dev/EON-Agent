from server.models import IncidentState, IncidentAction
from typing import List

def grade(state: IncidentState, action_history: List[IncidentAction]) -> float:
    # Score 1.0: correct service identified + correct fix_type + resolved in <=7 steps
    # Score 0.6-0.9: correct service, wrong fix_type, or resolved in 8-10 steps
    # Score 0.3-0.5: queried correct service logs/metrics but never fixed
    # Score 0.0-0.2: never identified root cause service
    
    steps = state.steps_taken
    root = state.root_cause_service
    resolved = state.resolved
    
    queried_root = False
    fixed_root = False
    wrong_fix = False
    
    for act in action_history:
        if act.action in ["query_logs", "check_metrics"] and act.target_service == root:
            queried_root = True
        if act.action in ["apply_fix", "rollback"] and act.target_service == root:
            fixed_root = True
            # Let's say we check if it actually mapped to resolution
            if not resolved:
                wrong_fix = True

    if resolved:
        if steps <= 7:
            return 0.95
        else:
            # 8 to 10 steps, or applied wrong fix before right fix
            return 0.78
    elif fixed_root and wrong_fix:
        return 0.62
    elif queried_root:
        return 0.38
    else:
        return 0.05
