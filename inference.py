import os
import json
import time
import asyncio
import httpx
from openai import AsyncOpenAI

BENCHMARK = "eon-agent"
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "eon-agent-image")

# The evaluator may provide SPACE_URL pointing to the already-running HF Space.
# If not set, we fall back to localhost and optionally start a Docker container.
SPACE_URL = os.getenv("SPACE_URL", "")

SYSTEM_PROMPT = """
You are an expert SRE (Site Reliability Engineer) responding to a production
incident inside the EON Agent environment.
You have access to these actions:
- list_services: See all services and their current health status
- query_logs(target_service): View recent logs for a specific service
- check_metrics(target_service): View error rate, latency, CPU, memory for a service
- get_dependencies(target_service): View what services a service depends on
- apply_fix(target_service, fix_type): Apply a fix.
    fix_type options: restart, rollback_config, scale_up, reroute
- rollback(target_service): Rollback the last deployment of a service
- escalate(): Escalate to senior on-call if you cannot resolve
- resolve(): Mark the incident as resolved after applying a fix

Strategy:
1. Start with list_services to see what is unhealthy
2. query_logs and check_metrics on suspicious services
3. Use get_dependencies to understand blast radius
4. Identify root cause, apply the correct fix
5. Call resolve() to end the episode

Respond with ONLY a JSON object:
{"action": "...", "target_service": "...", "fix_type": "..."}
"""


def _check_health(url, timeout=5):
    """Check if an environment URL is reachable."""
    try:
        with httpx.Client(timeout=timeout) as htest:
            res = htest.get(f"{url}/health")
            return res.status_code == 200
    except Exception:
        return False


def _resolve_env_url():
    """
    Determine the environment URL to connect to.
    Priority:
      1. SPACE_URL env var (set by the evaluator pointing to HF Space)
      2. Already-running localhost:7860 (e.g. evaluator started the container)
      3. Start a Docker container ourselves (local dev only)
    Returns (env_url, container_or_None).
    """
    # 1. Evaluator-provided Space URL
    if SPACE_URL:
        print(f"[DEBUG] Using evaluator-provided SPACE_URL: {SPACE_URL}", flush=True)
        return SPACE_URL.rstrip("/"), None

    # 2. Check if localhost is already reachable (evaluator may have started it)
    localhost = "http://localhost:7860"
    if _check_health(localhost):
        print("[DEBUG] Environment already running on localhost:7860", flush=True)
        return localhost, None

    # 3. Fall back to Docker for local development
    print(f"[DEBUG] Trying to start Docker container from image: {LOCAL_IMAGE_NAME}...", flush=True)
    try:
        import docker
        docker_client = docker.from_env()
        container = docker_client.containers.run(
            LOCAL_IMAGE_NAME,
            detach=True,
            ports={'7860/tcp': 7860}
        )
        print("[DEBUG] Waiting for container to become healthy...", flush=True)
        for _ in range(15):
            if _check_health(localhost):
                print("[DEBUG] Container is ready.", flush=True)
                return localhost, container
            time.sleep(2)
        print("[DEBUG] Container healthcheck timed out.", flush=True)
        container.stop()
        container.remove()
    except Exception as e:
        print(f"[DEBUG] Docker unavailable ({e}), skipping container start.", flush=True)

    # Last resort: assume localhost will work (evaluator may bring it up late)
    print("[DEBUG] Falling back to localhost:7860", flush=True)
    return localhost, None


async def run_inference():
    client = AsyncOpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    tasks = [
        ("single_fault", 10),
        ("cascading_failure", 15),
        ("ambiguous_multiregion", 20)
    ]

    env_url, container = _resolve_env_url()
    print(f"[DEBUG] Environment URL resolved to: {env_url}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            for task_name, max_steps in tasks:
                print(f"[START] task={task_name} env={BENCHMARK} model={MODEL_NAME}", flush=True)

                resp = await http.post(f"{env_url}/reset?task_name={task_name}&seed=123")
                state_data = resp.json()
                obs = state_data["observation"]

                rewards = []
                done = False
                steps = 0
                success = False

                messages = [{"role": "system", "content": SYSTEM_PROMPT.strip()}]

                while not done and steps < max_steps:
                    steps += 1

                    user_msg = f"""
Alert: {obs['alert']}
Services: {json.dumps(obs['services'], indent=2)}
Last action result: {obs['last_action_result']}
Step: {obs['step_count']} / {max_steps}
"""
                    messages.append({"role": "user", "content": user_msg.strip()})

                    try:
                        response = await client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=messages,
                            max_tokens=300,
                            temperature=0.3
                        )
                        content = response.choices[0].message.content
                        start_idx = content.find("{")
                        end_idx = content.rfind("}")
                        if start_idx != -1 and end_idx != -1:
                            action_data = json.loads(content[start_idx:end_idx+1])
                        else:
                            action_data = {"action": "list_services"}
                    except Exception:
                        action_data = {"action": "list_services"}

                    messages.append({"role": "assistant", "content": json.dumps(action_data)})

                    try:
                        step_resp = await http.post(f"{env_url}/step", json=action_data)
                        step_data = step_resp.json()
                    except Exception as e:
                        print(f"[STEP]  step={steps} action={json.dumps(action_data)} reward=0.00 done=false error={str(e)}", flush=True)
                        continue

                    obs = step_data["observation"]
                    reward = step_data["reward"]
                    done = step_data["done"]
                    rewards.append(reward)

                    action_str = action_data.get("action", "unknown")
                    reward_str = f"{reward:.2f}"
                    done_str = "true" if done else "false"

                    print(f"[STEP]  step={steps} action={action_str} reward={reward_str} done={done_str} error=null", flush=True)

                    if done:
                        success = obs["resolved"]
                        break

                if done:
                    try:
                        final_state_resp = await http.get(f"{env_url}/state")
                        final_state = final_state_resp.json()
                        final_score = final_state.get("score", sum(rewards))
                    except Exception:
                        final_score = sum(rewards)
                else:
                    final_score = 0.0

                success_str = "true" if success else "false"
                score_str = f"{final_score:.3f}"
                rewards_str = ",".join([f"{r:.2f}" for r in rewards])
                print(f"[END]   success={success_str} steps={steps} score={score_str} rewards={rewards_str}", flush=True)

    finally:
        if container:
            print("[DEBUG] Stopping and removing container...", flush=True)
            try:
                container.stop()
                container.remove()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(run_inference())
