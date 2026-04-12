# EON Agent — Production Incident Response Environment

> **OpenEnv Hackathon · Meta × Hugging Face · Solo Submission**

[![Phase 1](https://img.shields.io/badge/Phase%201-PASSED-brightgreen)](https://huggingface.co/spaces/Esh10/EON-Agent-Space)
[![Phase 2](https://img.shields.io/badge/Phase%202-PASSED-brightgreen)](https://huggingface.co/spaces/Esh10/EON-Agent-Space)
[![OpenEnv](https://img.shields.io/badge/OpenEnv-Validated-blue)](https://huggingface.co/spaces/Esh10/EON-Agent-Space)
[![HF Space](https://img.shields.io/badge/HuggingFace-Space-yellow)](https://huggingface.co/spaces/Esh10/EON-Agent-Space)

---

## What is EON Agent?

EON Agent is a synthetic **production incident response simulator** built for the OpenEnv standard. An LLM agent steps into the role of an on-call Site Reliability Engineer (SRE) — receiving a live pager alert, navigating a synthetic distributed system in a degraded state, and racing to diagnose and fix the root cause within a bounded number of steps.

Every real-world engineering organization at scale — from Meta to Google to any serious startup — runs this exact workflow daily. When a service goes down at 3 AM, someone has to query logs, trace dependency chains, correlate metrics across regions, and apply the right fix fast. EON Agent asks: **can an LLM do that?**

The environment is fully synthetic and deterministic. It generates realistic service topologies, coherent log streams, and meaningful metrics without touching any real infrastructure. All scenarios are seeded and reproducible, making it a clean benchmark for evaluating autonomous diagnostic reasoning in AI agents.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              LLM Agent (inference.py)       │
│   OpenAI Client · Structured JSON actions   │
└────────────────────┬────────────────────────┘
                     │ POST /step  GET /state
                     ▼
┌─────────────────────────────────────────────┐
│           FastAPI Environment Server         │
│         /reset  /step  /state  /health       │
└──────┬──────────────┬──────────────┬─────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌──────────────┐  ┌───────────────┐
│ Scenario │  │    Action    │  │    Reward     │
│  Engine  │  │   Executor   │  │   Calculator  │
│(seed det)│  │ (tool calls) │  │ (graders x3)  │
└──────────┘  └──────────────┘  └───────────────┘
```

- **Scenario Engine** — Generates deterministic incident states, fake logs, and metrics from a seed. Same seed always produces the same scenario.
- **Action Executor** — Simulates SRE tool calls: log queries, metric checks, dependency tracing, and infrastructure fixes.
- **Reward Calculator** — Computes partial and final rewards across four dimensions: diagnosis, isolation, fix correctness, and step efficiency.
- **FastAPI Server** — Exposes the full OpenEnv interface at port 7860, compatible with the `openenv validate` spec.

---

## Action Space

| Action | Parameters | Description | Reward Signal |
|--------|-----------|-------------|---------------|
| `list_services` | — | Lists all services with current health status | `0.0` (neutral, always safe) |
| `query_logs` | `target_service` | Fetches the 10 most recent log lines for a service | `+0.05` if relevant to root cause · `-0.02` if redundant |
| `check_metrics` | `target_service` | Returns error rate, latency p99, RPS, CPU%, MEM% | `+0.05` if service is degraded · `-0.02` if redundant |
| `get_dependencies` | `target_service` | Returns upstream and downstream service relationships | `+0.1` for tracing toward root cause |
| `apply_fix` | `target_service`, `fix_type` | Applies a targeted fix to a service | `+0.4` correct service + fix · `+0.1` correct service wrong fix · `-0.05` wrong service |
| `rollback` | `target_service` | Rolls back the last config deployment on a service | Equivalent to `apply_fix` with `fix_type=rollback_config` |
| `escalate` | — | Hands off to a human operator | Ends episode · score capped at `0.3` |
| `resolve` | — | Marks the incident as closed | Ends episode · triggers final score calculation |

**Valid `fix_type` values:** `restart` · `rollback_config` · `scale_up` · `reroute`

---

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `alert` | `string` | The pager alert text that triggered the incident |
| `services` | `list[ServiceStatus]` | All services with name, status, error\_rate, latency\_p99\_ms, region |
| `last_action_result` | `string` | Simulated terminal output from the last action |
| `step_count` | `int` | Number of steps taken in the current episode |
| `resolved` | `bool` | Whether the root cause has been successfully mitigated |
| `hint_available` | `bool` | Becomes `true` after 50% of max steps — models realistic "time pressure" |

**ServiceStatus fields:** `name · status (healthy/degraded/down) · error_rate · latency_p99_ms · region`

---

## Tasks

### Task 1 — `single_fault` · Easy · Max 10 steps

A single microservice has failed. Logs and metrics unambiguously point to one root cause — a randomly selected service with a randomly selected fault type (OOM kill, disk full, certificate expired, etc.). Healthy services produce normal INFO log noise. The agent must identify the right service and apply the correct fix.

**Why it's easy:** One clear signal, no noise from other services, direct mapping from log content to action.

**Expected agent path:** `list_services` → `query_logs(faulty_service)` → `apply_fix(faulty_service, fix_type)` → `resolve()`

---

### Task 2 — `cascading_failure` · Medium · Max 15 steps

A downstream dependency failure has propagated across 3 services. One root service (e.g. `database-primary`) has an actual fault. Two downstream services show degraded metrics and timeout errors as a consequence. One of those downstream services is a red herring with noisy logs.

**Why it's medium:** Multiple degraded signals, the alert names a symptom not the cause, and fixing a downstream service wastes steps and gives partial credit only.

**Expected agent path:** `list_services` → `check_metrics(degraded_svc)` → `get_dependencies(degraded_svc)` → `query_logs(root_svc)` → `apply_fix(root_svc, fix_type)` → `resolve()`

---

### Task 3 — `ambiguous_multiregion` · Hard · Max 20 steps

Two simultaneous degraded signals appear across `us-east` and `eu-west` — but with *different* error messages in each region. The root cause is a bad config pushed by `config-service` 45 minutes ago. Critically, `config-service` itself appears **healthy** (low error rate, low latency). The two regions surface different failure modes from the same misconfigured key.

**Why it's hard:** The root cause service looks healthy, the symptoms are superficially unrelated, and the correct fix (`rollback_config` on `config-service`) requires correlating evidence across regions rather than fixing what's obviously broken. Frontier models score ~0.31 on this task.

**Expected agent path:** `list_services` → `query_logs(api-gateway-us-east)` → `query_logs(api-gateway-eu-west)` → `get_dependencies(api-gateway-us-east)` → `query_logs(config-service)` → `rollback(config-service)` → `resolve()`

---

## Reward Function

The final reward (always in `[0.0, 1.0]`) is computed across four components at episode end:

| Component | Weight | Criteria |
|-----------|--------|----------|
| **Diagnosis** | 30% | Did the agent query logs or metrics for the actual root cause service? |
| **Isolation** | 20% | Did the agent use `get_dependencies` to trace the blast radius? |
| **Fix** | 40% | Was the final fix applied to the correct service with the correct fix type? |
| **Efficiency** | 10% | `max(0, 1 - steps_taken / max_steps)` — fewer steps = higher score |

Scores are **continuous**, not binary. An agent that diagnoses correctly but applies the wrong fix still scores above an agent that acted randomly. Partial progress is always rewarded.

**Step-level rewards** provide dense signal throughout the episode — the agent doesn't have to wait until the end to learn whether it's on the right track.

---

## Scenario Engine Design

All scenarios are **deterministic given a seed** — `random.Random(seed)` is used throughout. Same seed always produces the same services, logs, metrics, and fault. Different seeds produce meaningfully different scenarios with different root cause services, fault types, and alert texts.

**Fake logs are realistic:**
- ISO 8601 timestamps
- Service name in brackets
- Mix of `ERROR`, `WARN`, and `INFO` lines
- Root cause service logs contain a clear failure signal
- Healthy services emit normal request traffic noise
- Cascading services show timeout errors pointing upstream

**Fake metrics are coherent:**
- Degraded/down services: `error_rate > 0.3`, `latency_p99 > 800ms`
- Downstream-affected services: `error_rate 0.1–0.3`, elevated latency
- Healthy services: `error_rate < 0.05`, `latency < 150ms`

---

## Setup

### Local

```bash
git clone https://github.com/S-Eshwar-fut-dev/EON-Agent
cd EON-Agent
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Then visit `http://localhost:7860` or call the API directly.

### Docker

```bash
docker build -t eon-agent .
docker run -p 7860:7860 eon-agent
```

### API Quick Test

```bash
# Reset to task 1
curl -X POST "http://localhost:7860/reset?task_name=single_fault&seed=42"

# Take a step
curl -X POST "http://localhost:7860/step" \
  -H "Content-Type: application/json" \
  -d '{"action": "list_services"}'

# Get full state (includes hidden root cause — for graders/eval)
curl http://localhost:7860/state

# Health check
curl http://localhost:7860/health
```

---

## Running the Inference Script

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_your_token_here"

python inference.py
```

The script runs all 3 tasks sequentially and emits structured logs:

```
[START] task=single_fault env=eon-agent model=Qwen/Qwen2.5-72B-Instruct
[STEP]  step=1 action=list_services reward=0.00 done=false error=null
[STEP]  step=2 action=query_logs reward=0.05 done=false error=null
[STEP]  step=3 action=apply_fix reward=0.40 done=true error=null
[END]   success=true steps=3 score=0.823 rewards=0.00,0.05,0.40

[START] task=cascading_failure env=eon-agent model=Qwen/Qwen2.5-72B-Instruct
...
```

**Environment variables:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HF_TOKEN` | Yes | — | Your Hugging Face API token |
| `API_BASE_URL` | No | `https://router.huggingface.co/v1` | LLM inference endpoint |
| `MODEL_NAME` | No | `Qwen/Qwen2.5-72B-Instruct` | Model identifier |
| `SPACE_URL` | No | — | Set by evaluator to point at the live HF Space |

---

## Baseline Scores

Scores produced by running `inference.py` against `Qwen/Qwen2.5-72B-Instruct` with `seed=123`:

| Task | Difficulty | Model | Score | Steps Used | Max Steps |
|------|-----------|-------|-------|-----------|-----------|
| `single_fault` | Easy | Qwen2.5-72B | ~0.72 | 7 | 10 |
| `cascading_failure` | Medium | Qwen2.5-72B | ~0.54 | 12 | 15 |
| `ambiguous_multiregion` | Hard | Qwen2.5-72B | ~0.31 | 19 | 20 |

The hard task is intentionally difficult — even frontier-class models struggle to correlate two different error signatures back to a shared root cause that appears healthy on the surface.

---

## Project Structure

```
eon-agent/
├── Dockerfile                    # HF Space compliant (UID 1000 user)
├── openenv.yaml                  # OpenEnv spec metadata
├── inference.py                  # Baseline inference script (root level)
├── requirements.txt
├── pyproject.toml
├── README.md
└── server/
    ├── app.py                    # FastAPI app — /reset /step /state /health
    ├── models.py                 # Pydantic v2 typed models
    ├── environment.py            # Core reset/step/state logic
    ├── scenario_engine.py        # Deterministic scenario generation
    ├── action_executor.py        # Tool call simulation + partial rewards
    ├── reward.py                 # Final score computation
    └── tasks/
        ├── task1_single_fault.py # Easy grader
        ├── task2_cascading.py    # Medium grader
        └── task3_ambiguous.py    # Hard grader
```

---

## OpenEnv Spec Compliance

| Requirement | Status |
|-------------|--------|
| Typed `Observation`, `Action`, `Reward` Pydantic models | ✅ |
| `POST /reset` returns clean initial observation | ✅ |
| `POST /step` returns observation, reward, done, info | ✅ |
| `GET /state` returns full episode state | ✅ |
| `openenv.yaml` with metadata and task definitions | ✅ |
| Reward strictly in `[0.0, 1.0]` | ✅ |
| 3 tasks with deterministic graders | ✅ |
| Partial reward signal (not just binary end-of-episode) | ✅ |
| `GET /health` liveness probe | ✅ |
| Dockerfile builds and runs cleanly | ✅ |
| HF Space deployed and responding | ✅ |

---

## Limitations and Future Work

- **Fixed service catalog** — The 10 services are consistent across scenarios. Future work: procedurally generate service names and topology per seed for more variety.
- **Static time elements** — Log timestamps are simulated but do not model real-time progression. A future version could simulate rolling log windows.
- **No noisy false-alarm pipeline** — Real SRE environments generate many spurious alerts. Adding false alarm scenarios would improve robustness training.
- **Single agent, no collaboration** — Multi-agent incident response (one agent per region) is a natural extension.
- **Richer fix outcomes** — Currently fixes are binary (worked/didn't). Real infrastructure responds with partial restarts, slow recoveries, and side effects worth modeling.

---

## Links

- **HF Space:** https://huggingface.co/spaces/Esh10/EON-Agent-Space
- **GitHub:** https://github.com/S-Eshwar-fut-dev/EON-Agent

---

*Built solo for the Meta × Hugging Face OpenEnv Hackathon · April 2026*fixed architectures instead of procedurally generated topologies).
- Time elements are heavily static to support deterministic step outcomes.
- Future work: Include auto-scaling simulated latency curves, unstructured documentation artifacts, and noisy false-alarm pipelines to improve agent robustness.
