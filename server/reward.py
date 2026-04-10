from server.models import IncidentReward, ScenarioState, IncidentAction
from typing import List

class RewardCalculator:
    
    def compute_final_score(
        self,
        state: ScenarioState,
        action_history: List[IncidentAction],
        resolved: bool,
        steps_taken: int,
        max_steps: int
    ) -> IncidentReward:
        
        task_name = state.state.task_name
        
        if task_name == "single_fault":
            from server.tasks.task1_single_fault import grade
        elif task_name == "cascading_failure":
            from server.tasks.task2_cascading import grade
        elif task_name == "ambiguous_multiregion":
            from server.tasks.task3_ambiguous import grade
        else:
            def grade(s, a): return 0.0

        total_score = grade(state.state, action_history)
        
        # Calculate genuine efficiency
        efficiency = max(0.0, 0.1 * (1.0 - steps_taken / max_steps)) if resolved else 0.0
        
        # Determine actual breakdown using standard rules to populate the dictionary
        diagnosis = self._score_diagnosis(state, action_history)
        isolation = self._score_isolation(state, action_history)
        fix = self._score_fix(state, action_history, resolved)
        
        # Scale remaining components so the sum strictly matches total_score from grade()
        raw_sum = diagnosis + isolation + fix
        target_sum = total_score - efficiency
        
        breakdown = {}
        if raw_sum > 0 and target_sum > 0:
            scale = target_sum / raw_sum
            breakdown["diagnosis"] = round(diagnosis * scale, 3)
            breakdown["isolation"] = round(isolation * scale, 3)
            breakdown["fix"] = round(fix * scale, 3)
        else:
            # Fallback if raw_sum is 0 but task gave a score (e.g. guessed correctly blindly)
            breakdown["diagnosis"] = round(target_sum * 0.3, 3)
            breakdown["isolation"] = round(target_sum * 0.1, 3)
            breakdown["fix"] = round(target_sum * 0.6, 3)
            
        breakdown["efficiency"] = round(efficiency, 3)
        
        # Fix floating point rounding exactly
        final_sum = sum(breakdown.values())
        diff = total_score - final_sum
        breakdown["fix"] = round(breakdown["fix"] + diff, 3)
        
        value = min(max(sum(breakdown.values()), 0.0), 1.0)
        
        return IncidentReward(value=value, breakdown=breakdown)

    def _score_diagnosis(self, state: ScenarioState, action_history: List[IncidentAction]) -> float:
        root_cause = state.state.root_cause_service
        for a in action_history:
            if a.action in ["query_logs", "check_metrics"]:
                if a.target_service == root_cause or (root_cause == "config-service" and a.target_service and "api-gateway" in a.target_service):
                    return 0.3
        return 0.0

    def _score_isolation(self, state: ScenarioState, action_history: List[IncidentAction]) -> float:
        for a in action_history:
            if a.action == "get_dependencies":
                return 0.2
        return 0.0

    def _score_fix(self, state: ScenarioState, action_history: List[IncidentAction], resolved: bool) -> float:
        if resolved:
            return 0.4
        return 0.0
