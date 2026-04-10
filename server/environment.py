from server.models import IncidentState, StepResult, IncidentObservation, IncidentAction, ScenarioState
from server.scenario_engine import ScenarioEngine
from server.action_executor import ActionExecutor
from server.reward import RewardCalculator
from typing import Optional, List

class IncidentEnvironment:
    def __init__(self):
        self._state: Optional[ScenarioState] = None
        self._action_history: List[IncidentAction] = []
        self._scenario_engine = ScenarioEngine()
        self._executor = ActionExecutor()
        self._reward_calc = RewardCalculator()
        self._current_task: str = "single_fault"
        self._seed: int = 42

    def reset(self, task_name: str = "single_fault", seed: int = 42) -> StepResult:
        self._current_task = task_name
        self._seed = seed
        self._action_history = []
        
        if task_name == "single_fault":
            self._state = self._scenario_engine.generate_task1(seed)
        elif task_name == "cascading_failure":
            self._state = self._scenario_engine.generate_task2(seed)
        elif task_name == "ambiguous_multiregion":
            self._state = self._scenario_engine.generate_task3(seed)
        else:
            self._state = self._scenario_engine.generate_task1(seed)
            
        obs = self._build_observation()
        return StepResult(observation=obs, reward=0.0, done=False, info={})

    def step(self, action: IncidentAction) -> StepResult:
        if self._state is None:
            raise RuntimeError("Call reset() first")
        
        self._state.state.steps_taken += 1
        self._action_history.append(action)
        
        result_text, step_reward = self._executor.execute(action, self._state)
        self._state.last_action_result = result_text
        
        done = (
            self._state.state.resolved or
            action.action == "escalate" or
            action.action == "resolve" or
            self._state.state.steps_taken >= self._state.state.max_steps
        )
        
        if done:
            final_reward = self._reward_calc.compute_final_score(
                self._state, self._action_history,
                self._state.state.resolved,
                self._state.state.steps_taken,
                self._state.state.max_steps
            )
            self._state.state.score = final_reward.value
            reward = final_reward.value
        else:
            reward = step_reward
            
        obs = self._build_observation()
        return StepResult(observation=obs, reward=reward, done=done, info={
            "steps_taken": self._state.state.steps_taken,
            "max_steps": self._state.state.max_steps,
            "resolved": self._state.state.resolved
        })

    def state(self) -> IncidentState:
        if not self._state:
            raise RuntimeError("Call reset() first")
        return self._state.state

    def _build_observation(self) -> IncidentObservation:
        if not self._state:
            raise RuntimeError("Call reset() first")
        hint_available = self._state.state.steps_taken >= (self._state.state.max_steps * 0.5)
        return IncidentObservation(
            alert=self._state.alert_text,
            services=self._state.services,
            last_action_result=self._state.last_action_result,
            step_count=self._state.state.steps_taken,
            resolved=self._state.state.resolved,
            hint_available=hint_available
        )
