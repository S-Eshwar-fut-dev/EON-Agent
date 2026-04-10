---
title: EON Agent
emoji: 🔥
colorFrom: red
colorTo: orange
sdk: docker
pinned: false
tags:
  - openenv
  - sre
  - incident-response
  - distributed-systems
  - eon-agent
---

# EON Agent — Production Incident Response Environment

The EON Agent is a synthetic production incident response simulator designed for the Meta x OpenEnv Hugging Face hackathon. It evaluates LLM agents on their ability to act as on-call Site Reliability Engineers (SREs), diagnosing and resolving complex distributed system failures under bounded step constraints.

Autonomous incident response is an incredibly valuable area of research for the RL and agent community. As distributed systems grow in complexity, the mean time to resolution (MTTR) is increasingly bottlenecked by human cognition speed. By providing a sandbox where AI models can practice troubleshooting—querying logs, examining metrics, and tracing dependency chains—researchers can develop agents with strong infrastructural intuition and diagnostic reasoning. This environment serves as a rigorous benchmark for such capabilities.

## Architecture Overview

The system consists of a FastAPI server acting as the environment interface and an underlying deterministic state engine:
- **Scenario Engine:** Generates deterministic system states, logs, and metrics based on a seed.
- **Action Executor:** Simulates tools (observability querying, infrastructure fixes).
- **Environment API:** Exposes endpoints like `/reset`, `/step`, and `/state` for interaction.

## Action Space

| Action | Parameters | Description | Reward Signal |
|--------|------------|-------------|---------------|
| `list_services` | None | Lists all services and baseline health status | Neutral (+0.0) |
| `query_logs` | `target_service` | Fetch 10 latest log lines for a service | +0.05 if relevant to root cause, -0.02 if redundant |
| `check_metrics` | `target_service` | View error rate, latency, CPU, and RAM | +0.05 if relevant to root cause, -0.02 if redundant |
| `get_dependencies` | `target_service` | View upstream and downstream relationships | +0.1 for isolation tracing |
| `apply_fix` | `target_service`, `fix_type` | Apply a targeted fix on a service | +0.4 for correct fix/service, partial credit for mixed |
| `rollback` | `target_service` | Rollback configuration of a service | Equivalent to apply_fix type `rollback_config` |
| `escalate` | None | Escalate to human operator | Caps score (max 0.3) |
| `resolve` | None | Mark episode as finished | Ends episode |

*Allowed `fix_type` values:* `restart`, `rollback_config`, `scale_up`, `reroute`.

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `alert` | string | Theoretical pager alert text |
| `services` | list of ServiceStatus | List of all services and their region/health summaries |
| `last_action_result` | string | String response simulating terminal/ui output |
| `step_count` | integer | Number of executed actions in the episode |
| `resolved` | boolean | True if root cause is successfully mitigated |
| `hint_available` | boolean | True if >50% max steps used |

## Tasks

1. **`single_fault` (Easy):** A single microservice is down. Logs and metrics unambiguously point to one root cause. The agent must identify the failing service and apply the correct fix within 10 steps.
2. **`cascading_failure` (Medium):** A downstream dependency failure has propagated to 3 services. The agent must trace the dependency chain, identify the origin, and apply a targeted fix within 15 steps. Wasting fixes on downstream symptoms incurs a penalty.
3. **`ambiguous_multiregion` (Hard):** Two simultaneous degraded signals appear across regions due to a shared root cause (e.g., config rollout). The agent must correlate signals across services and regions to rollback the configuration on the hidden root-cause service. Max steps: 20.

## Reward Function

The overall reward (0.0 to 1.0) mathematically assesses the complete response workflow:
- **Diagnosis (30%):** Queried logs and metrics for the correct root cause service.
- **Isolation (20%):** Used dependency graphs to understand blast radius.
- **Fix (40%):** Successfully and exclusively mitigated the root cause.
- **Efficiency (10%):** Time-to-resolution, measured in steps saved against max steps.

## Setup

### Local Execution
```bash
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 7860
```

### Docker
```bash
docker build -t eon-agent .
docker run -p 7860:7860 eon-agent
```

## Inference Script

To evaluate models locally or against Hugging Face inference endpoints:
```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
python inference.py
```

## Baseline Scores

| Task                 | Model          | Score | Steps |
|----------------------|----------------|-------|-------|
| single_fault         | Qwen2.5-72B    | ~0.72 | 7     |
| cascading_failure    | Qwen2.5-72B    | ~0.54 | 12    |
| ambiguous_multiregion| Qwen2.5-72B    | ~0.31 | 19    |

## Limitations and Future Work
- Hardcoded string dependencies (e.g., fixed architectures instead of procedurally generated topologies).
- Time elements are heavily static to support deterministic step outcomes.
- Future work: Include auto-scaling simulated latency curves, unstructured documentation artifacts, and noisy false-alarm pipelines to improve agent robustness.
