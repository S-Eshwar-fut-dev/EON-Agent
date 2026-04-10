from fastapi import FastAPI
from server.models import IncidentAction, StepResult, IncidentState
from server.environment import IncidentEnvironment

app = FastAPI(title="EON Agent", version="1.0.0")
env = IncidentEnvironment()

@app.get("/")
def read_root():
    return {"message": "EON Agent Environment is running! Use /reset and /step for inference."}

@app.post("/reset")
def reset(task_name: str = "single_fault", seed: int = 42) -> StepResult:
    return env.reset(task_name=task_name, seed=seed)

@app.post("/step")
def step(action: IncidentAction) -> StepResult:
    return env.step(action)

@app.get("/state")
def state() -> IncidentState:
    return env.state()

@app.get("/health")
def health():
    return {"status": "ok", "env": "eon-agent"}
