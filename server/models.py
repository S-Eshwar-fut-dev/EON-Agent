from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Literal, Dict, List, Optional, Any, Set

class ServiceStatus(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "down"]
    error_rate: float
    latency_p99_ms: float
    region: str

class IncidentObservation(BaseModel):
    alert: str
    services: List[ServiceStatus]
    last_action_result: str
    step_count: int
    resolved: bool
    hint_available: bool

class IncidentAction(BaseModel):
    action: str = Field(...)
    target_service: Optional[str] = None
    fix_type: Optional[str] = None
    parameters: Optional[Dict] = None

    @field_validator("action", mode="before")
    @classmethod
    def fallback_invalid_action(cls, v: Any) -> Any:
        valid_actions = ["query_logs", "check_metrics", "list_services", "get_dependencies", "apply_fix", "rollback", "escalate", "resolve"]
        if v not in valid_actions:
            return "list_services"
        return v

class IncidentReward(BaseModel):
    value: float
    breakdown: Dict[str, float]

class IncidentState(BaseModel):
    task_name: str
    scenario_id: str
    root_cause_service: str
    root_cause_type: str
    steps_taken: int
    max_steps: int
    resolved: bool
    score: float

class ScenarioState(BaseModel):
    model_config = ConfigDict(extra='allow')
    state: IncidentState
    services: List[ServiceStatus]
    fake_logs: Dict[str, List[str]]
    fake_metrics: Dict[str, Dict]
    dependency_graph: Dict[str, List[str]]
    correct_action_sequence: List[Dict]
    alert_text: str
    last_action_result: str = "Environment initialized. Awaiting action."
    logs_queried: List[str] = Field(default_factory=list)
    metrics_queried: List[str] = Field(default_factory=list)

class StepResult(BaseModel):
    observation: IncidentObservation
    reward: float
    done: bool
    info: Dict
