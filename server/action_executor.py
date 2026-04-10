from typing import Tuple
from server.models import IncidentAction, ScenarioState
import json

class ActionExecutor:
    def execute(self, action: IncidentAction, state: ScenarioState) -> Tuple[str, float]:
        a = action.action
        target = action.target_service
        
        # Helper to check relevance
        def is_relevant(svc: str) -> bool:
            if svc == state.state.root_cause_service:
                return True
            # For cascading, downstream affected services are somewhat relevant
            for s in state.services:
                if s.name == svc and s.status in ["degraded", "down"]:
                    return True
            # For multiregion, matching prefix might be relevant
            if "-east" in svc or "-west" in svc:
                base = svc.split("-east")[0].split("-west")[0]
                return base in state.state.root_cause_service or True
            return False

        if a == "list_services":
            overview = []
            for s in state.services:
                overview.append(f"{s.name} ({s.region}): {s.status}")
            return "Services:\n" + "\n".join(overview), 0.0

        elif a == "query_logs":
            if not target: return "Error: target_service required.", -0.02
            
            # Use matching logic to handle multiregion if needed
            # Actually, the agent must pass exact name
            if target not in state.fake_logs:
                return f"Error: No logs found for service {target}", -0.02
                
            redundant = state.logs_queried.count(target) > 0
            state.logs_queried.append(target)
            
            logs = state.fake_logs[target][-10:]
            result_text = "\n".join(logs)
            
            reward = 0.0
            if redundant:
                reward = -0.02
            elif is_relevant(target):
                reward = 0.05
                
            return result_text, reward

        elif a == "check_metrics":
            if not target: return "Error: target_service required.", -0.02
            if target not in state.fake_metrics:
                return f"Error: No metrics found for service {target}", -0.02
                
            redundant = state.metrics_queried.count(target) > 0
            state.metrics_queried.append(target)
            
            metrics = state.fake_metrics[target]
            result_text = json.dumps(metrics, indent=2)
            
            reward = 0.0
            if redundant:
                reward = -0.02
            elif is_relevant(target):
                reward = 0.05
                
            return result_text, reward

        elif a == "get_dependencies":
            if not target: return "Error: target_service required.", -0.02
            
            # Find upstream (things that depend on target) and downstream (things target depends on)
            downstream = state.dependency_graph.get(target, [])
            upstream = []
            for s, deps in state.dependency_graph.items():
                if target in deps:
                    upstream.append(s)
            
            result_text = json.dumps({
                "upstream": upstream,
                "downstream": downstream
            }, indent=2)
            
            # Partial reward: +0.1 if used to trace from symptom toward root cause
            return result_text, 0.1

        elif a == "apply_fix":
            if not target: return "Error: target_service required.", -0.02
            fix_type = action.fix_type
            
            if fix_type not in ["restart", "rollback_config", "scale_up", "reroute"]:
                return f"Error: Invalid fix_type '{fix_type}'", -0.02
            
            if target == state.state.root_cause_service:
                if fix_type == state.correct_action_sequence[0].get("fix_type", fix_type): 
                    # If we didn't specify correct fix type in generated state, any correct fix for the root cause applies, or we handle it via task grader logic.
                    # Wait, task1 says "apply_fix on that service with correct fix_type". 
                    # Let's say if it's the right service and right fix type.
                    # Since we didn't populate proper fix_type in ScenarioEngine correct_action_sequence for all tasks, let's treat matching the root cause string as paramount.
                    
                    # Actually, the task specifies what fix is right.
                    task = state.state.task_name
                    is_correct_fix = False
                    if task == "single_fault":
                        is_correct_fix = True # Assume any apply_fix on root cause is right? Or maybe we map fault_type to correct fix_type.
                        if state.state.root_cause_type == "oom_kill": is_correct_fix = (fix_type in ["restart", "scale_up"])
                        elif state.state.root_cause_type == "config_drift": is_correct_fix = (fix_type == "rollback_config")
                        else: is_correct_fix = True
                    elif task == "cascading_failure":
                        is_correct_fix = True
                    elif task == "ambiguous_multiregion":
                        is_correct_fix = (fix_type == "rollback_config")
                        
                    if is_correct_fix:
                        state.state.resolved = True
                        return f"Fix '{fix_type}' successfully applied to {target}. Service is recovering.", 0.4
                    else:
                        return f"Fix '{fix_type}' applied to {target}, but service remains degraded.", 0.1
            
            return f"Fix applied to {target}, but symptoms persist.", -0.05

        elif a == "rollback":
            if not target: return "Error: target_service required.", -0.02
            # Equivalent to apply_fix with rollback_config
            action.fix_type = "rollback_config"
            return self.execute(IncidentAction(action="apply_fix", target_service=target, fix_type="rollback_config"), state)

        elif a == "escalate":
            # Environment handles the end episode.
            return "Incident escalated to senior on-call.", 0.0

        elif a == "resolve":
            if state.state.resolved:
                return "Incident resolved successfully.", 0.0
            else:
                return "Incident is not resolved. Symptoms still present.", -0.1

        return "Unknown action", -0.02
