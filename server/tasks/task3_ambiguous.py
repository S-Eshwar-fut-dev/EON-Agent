from server.models import IncidentState, IncidentAction
from typing import List

def grade(state: IncidentState, action_history: List[IncidentAction]) -> float:
    steps = state.steps_taken
    root = state.root_cause_service # config-service
    resolved = state.resolved
    
    queried_root = False
    wrong_fix = False
    fixed_symptom = False
    
    for act in action_history:
        if act.action in ["query_logs", "check_metrics"]:
            if act.target_service == root:
                queried_root = True
        
        if act.action == "apply_fix" and act.target_service == root:
            if act.fix_type != "rollback_config":
                wrong_fix = True
                
        if act.action in ["apply_fix", "rollback"]:
            if act.target_service and "api-gateway" in act.target_service:
                fixed_symptom = True

    if resolved and steps <= 15:
        return 0.95
    elif resolved and steps > 15:
        return 0.78
    elif queried_root and wrong_fix:
        return 0.58
    elif fixed_symptom:
        return 0.28
    else:
        return 0.05
