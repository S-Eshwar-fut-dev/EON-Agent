import random
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from server.models import ScenarioState, IncidentState, ServiceStatus

class ScenarioEngine:
    SERVICES = [
        "auth-service", "api-gateway", "user-service", "payment-service",
        "notification-service", "database-primary", "database-replica",
        "cache-layer", "message-queue", "config-service"
    ]
    
    FAULT_TYPES = [
        "oom_kill",           
        "config_drift",       
        "connection_pool_exhausted",
        "downstream_timeout",
        "disk_full",
        "certificate_expired",
        "rate_limit_exceeded",
        "network_partition"
    ]

    def _generate_iso_timestamp(self, r: random.Random, minutes_ago: int) -> str:
        base_time = datetime(2024, 1, 1, 12, 0, 0) - timedelta(minutes=minutes_ago, seconds=r.randint(0, 59))
        return base_time.isoformat() + "Z"
        
    def _create_healthy_logs(self, r: random.Random, service: str) -> List[str]:
        logs = []
        for i in range(10, 0, -1):
            ts = self._generate_iso_timestamp(r, i)
            logs.append(f"{ts} [{service}] INFO - Connection established. Status OK.")
        return logs

    def generate_task1(self, seed: int) -> ScenarioState:
        """Single service fault. Root cause is unambiguous from logs."""
        r = random.Random(seed)
        faulty_svc = r.choice(self.SERVICES)
        fault_type = r.choice(self.FAULT_TYPES)
        
        services = []
        fake_logs = {}
        fake_metrics = {}
        dependency_graph = {s: [] for s in self.SERVICES}
        
        # Build dependency graph (tree-like for simplicity)
        dependency_graph["api-gateway"] = ["auth-service", "user-service", "payment-service"]
        dependency_graph["user-service"] = ["database-primary", "cache-layer"]
        dependency_graph["payment-service"] = ["database-primary", "message-queue"]
        dependency_graph["database-primary"] = ["database-replica"]
        
        for svc in self.SERVICES:
            if svc == faulty_svc:
                status = "down"
                error_rate = round(r.uniform(0.6, 1.0), 2)
                latency = round(r.uniform(1000, 3000), 2)
                
                logs = self._create_healthy_logs(r, svc)[:5]
                # Add failure logs
                for i in range(5, 0, -1):
                    ts = self._generate_iso_timestamp(r, i)
                    logs.append(f"{ts} [{svc}] ERROR - Critical failure: {fault_type} detected. Process terminated.")
                fake_logs[svc] = logs
            else:
                status = "healthy"
                error_rate = round(r.uniform(0.0, 0.05), 2)
                latency = round(r.uniform(10, 150), 2)
                fake_logs[svc] = self._create_healthy_logs(r, svc)
                
            region = "us-east-1"
            services.append(ServiceStatus(
                name=svc, status=status, error_rate=error_rate, latency_p99_ms=latency, region=region
            ))
            
            fake_metrics[svc] = {
                "error_rate": error_rate,
                "latency_p99": latency,
                "rps": r.randint(100, 5000),
                "cpu_percent": round(r.uniform(10, 95) if svc == faulty_svc else r.uniform(10, 40), 1),
                "mem_percent": round(r.uniform(80, 99) if fault_type == "oom_kill" else r.uniform(20, 60), 1)
            }
            
        alert_text = f"PAGER_ALERT: High error rate detected on {faulty_svc}"
        
        state = IncidentState(
            task_name="single_fault",
            scenario_id=f"task1_{seed}_{faulty_svc}",
            root_cause_service=faulty_svc,
            root_cause_type=fault_type,
            steps_taken=0,
            max_steps=10,
            resolved=False,
            score=0.0
        )
        
        return ScenarioState(
            state=state,
            services=services,
            fake_logs=fake_logs,
            fake_metrics=fake_metrics,
            dependency_graph=dependency_graph,
            correct_action_sequence=[{"action": "apply_fix", "target_service": faulty_svc}],
            alert_text=alert_text
        )

    def generate_task2(self, seed: int) -> ScenarioState:
        """Cascading failure. 3 services affected, only one is root cause."""
        r = random.Random(seed)
        
        # Valid roots for cascading
        roots = [("database-primary", ["user-service", "payment-service"]),
                 ("cache-layer", ["user-service"]),
                 ("auth-service", ["api-gateway"])]
                 
        root_svc, downstream = r.choice(roots)
        fault_type = "connection_pool_exhausted"
        
        # We need exactly 3 affected services. 
        # If downstream length < 2, add api-gateway to make it cascade further
        affected = set([root_svc] + downstream)
        if len(affected) < 3:
            affected.add("api-gateway")
            
        dependency_graph = {s: [] for s in self.SERVICES}
        dependency_graph["api-gateway"] = ["auth-service", "user-service", "payment-service"]
        dependency_graph["user-service"] = ["database-primary", "cache-layer"]
        dependency_graph["payment-service"] = ["database-primary", "message-queue"]
        dependency_graph["database-primary"] = ["database-replica"]
        
        services = []
        fake_logs = {}
        fake_metrics = {}
        
        for svc in self.SERVICES:
            if svc == root_svc:
                status = "degraded"
                error_rate = round(r.uniform(0.4, 0.8), 2)
                latency = round(r.uniform(2000, 5000), 2)
                logs = self._create_healthy_logs(r, svc)[:2]
                for i in range(8, 0, -1):
                    ts = self._generate_iso_timestamp(r, i)
                    logs.append(f"{ts} [{svc}] ERROR - {fault_type}: Reached max connections.")
                fake_logs[svc] = logs
            elif svc in affected:
                status = "degraded"
                error_rate = round(r.uniform(0.1, 0.3), 2)
                latency = round(r.uniform(1000, 2000), 2)
                logs = self._create_healthy_logs(r, svc)[:5]
                for i in range(5, 0, -1):
                    ts = self._generate_iso_timestamp(r, i)
                    logs.append(f"{ts} [{svc}] WARN - Timeout waiting for response from {root_svc}")
                fake_logs[svc] = logs
            else:
                status = "healthy"
                error_rate = round(r.uniform(0.0, 0.05), 2)
                latency = round(r.uniform(10, 150), 2)
                fake_logs[svc] = self._create_healthy_logs(r, svc)
                
            region = "us-east-1"
            services.append(ServiceStatus(
                name=svc, status=status, error_rate=error_rate, latency_p99_ms=latency, region=region
            ))
            
            fake_metrics[svc] = {
                "error_rate": error_rate,
                "latency_p99": latency,
                "rps": r.randint(100, 5000),
                "cpu_percent": round(r.uniform(60, 90) if svc in affected else r.uniform(10, 40), 1),
                "mem_percent": round(r.uniform(20, 60), 1)
            }
            
        downstream_symptom = list(affected - {root_svc})[0]
        alert_text = f"PAGER_ALERT: Multiple service degradation detected. Primary symptom on {downstream_symptom}"
        
        state = IncidentState(
            task_name="cascading_failure",
            scenario_id=f"task2_{seed}_{root_svc}",
            root_cause_service=root_svc,
            root_cause_type=fault_type,
            steps_taken=0,
            max_steps=15,
            resolved=False,
            score=0.0
        )
        
        return ScenarioState(
            state=state,
            services=services,
            fake_logs=fake_logs,
            fake_metrics=fake_metrics,
            dependency_graph=dependency_graph,
            correct_action_sequence=[{"action": "apply_fix", "target_service": root_svc}],
            alert_text=alert_text
        )

    def generate_task3(self, seed: int) -> ScenarioState:
        """Ambiguous multi-region. Same config service, different AZs."""
        r = random.Random(seed)
        root_svc = "config-service"
        fault_type = "config_drift"
        
        dependency_graph = {s: [] for s in self.SERVICES}
        for s in self.SERVICES:
            if s != "config-service":
                dependency_graph[s] = ["config-service"]
                
        # us-east and eu-west
        affected_services = [
            ("api-gateway", "us-east"),
            ("api-gateway", "eu-west")
        ]
        
        services = []
        fake_logs = {}
        fake_metrics = {}
        
        for name in self.SERVICES:
            if name == "api-gateway":
                for region in ["us-east", "eu-west"]:
                    status = "degraded"
                    error_rate = round(r.uniform(0.3, 0.6), 2)
                    latency = round(r.uniform(800, 1500), 2)
                    services.append(ServiceStatus(
                        name=f"{name}-{region}", status=status, error_rate=error_rate, latency_p99_ms=latency, region=region
                    ))
                    
                    logs = self._create_healthy_logs(r, f"{name}-{region}")[:6]
                    for i in range(4, 0, -1):
                        ts = self._generate_iso_timestamp(r, i + 45) # Config pushed 45 mins ago
                        err_str = "Invalid routing rules derived from config." if region == "us-east" else "Rate limit threshold missing from config."
                        logs.append(f"{ts} [{name}-{region}] ERROR - {err_str} Context: recent config sync.")
                    fake_logs[f"{name}-{region}"] = logs
                    
                    fake_metrics[f"{name}-{region}"] = {
                        "error_rate": error_rate, "latency_p99": latency,
                        "rps": r.randint(100, 5000), "cpu_percent": 45.0, "mem_percent": 30.0
                    }
            elif name == "config-service":
                status = "healthy" # Appears healthy!
                services.append(ServiceStatus(
                    name=name, status=status, error_rate=0.01, latency_p99_ms=50.0, region="global"
                ))
                logs = self._create_healthy_logs(r, name)[:8]
                ts = self._generate_iso_timestamp(r, 45)
                logs.append(f"{ts} [{name}] INFO - Pushed new global config v1.42.0 to all regions.")
                logs.append(f"{ts} [{name}] INFO - Sync completed successfully.")
                fake_logs[name] = logs
                fake_metrics[name] = {
                    "error_rate": 0.01, "latency_p99": 50.0, "rps": 10, "cpu_percent": 5.0, "mem_percent": 15.0
                }
            else:
                services.append(ServiceStatus(
                    name=name, status="healthy", error_rate=0.01, latency_p99_ms=30.0, region="global"
                ))
                fake_logs[name] = self._create_healthy_logs(r, name)
                fake_metrics[name] = {
                    "error_rate": 0.01, "latency_p99": 30.0, "rps": 10, "cpu_percent": 10.0, "mem_percent": 20.0
                }
                
        alert_text = "PAGER_ALERT: Simultaneous latency spikes on API Gateway in us-east and eu-west."
        
        state = IncidentState(
            task_name="ambiguous_multiregion",
            scenario_id=f"task3_{seed}_multiregion",
            root_cause_service=root_svc,
            root_cause_type=fault_type,
            steps_taken=0,
            max_steps=20,
            resolved=False,
            score=0.0
        )
        
        return ScenarioState(
            state=state,
            services=services,
            fake_logs=fake_logs,
            fake_metrics=fake_metrics,
            dependency_graph=dependency_graph,
            correct_action_sequence=[{"action": "rollback", "target_service": root_svc}],
            alert_text=alert_text
        )
