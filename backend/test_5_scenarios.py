import requests
import json
import traceback

SCENARIOS = {
    "1. OOMKilled": """Pod: payments-api
Status: CrashLoopBackOff
Restart Count: 17

Events:
Back-off restarting failed container
OOMKilled

Logs:
Java heap space error

Metrics:
Memory usage: 98%
Memory limit: 512Mi""",

    "2. ImagePullBackOff": """Pod: frontend-ui
Status: ImagePullBackOff
Restart Count: 0

Events:
Failed to pull image "registry.internal/frontend:v2.9.9": rpc error: code = NotFound
Error: ErrImagePull
Error: ImagePullBackOff

Logs:
(none)

Metrics:
CPU usage: 0%
Memory usage: 0%""",

    "3. Pending / Insufficient CPU": """Pod: data-processor
Status: Pending
Restart Count: 0

Events:
FailedScheduling: 0/5 nodes are available: 5 Insufficient cpu. preemption: 0/5 nodes are available: 5 No preemption victims found for incoming pod.

Logs:
(none)

Metrics:
Requested CPU: 16
Available Cluster CPU: 4""",

    "4. Readiness Probe Failure": """Pod: backend-auth
Status: Running
Restart Count: 3

Events:
Unhealthy: Readiness probe failed: HTTP probe failed with statuscode: 503

Logs:
[ERROR] Database connection timeout after 30000ms
[WARN] Health check endpoint returning 503 Service Unavailable

Metrics:
CPU usage: 45%
Memory usage: 30%""",

    "5. DNS / Service Connectivity": """Pod: inventory-service
Status: Running
Restart Count: 0

Events:
(normal pod startup events)

Logs:
[ERROR] Failed to connect to payment-gateway:50051
[ERROR] dial tcp: lookup payment-gateway on 10.96.0.10:53: no such host

Metrics:
CPU usage: 10%
Memory usage: 15%"""
}

URL = "http://localhost:8000/diagnose"

print("Starting 5 Scenario Test against running API...")

results = {}

for name, telemetry in SCENARIOS.items():
    print(f"Running: {name}")
    try:
        response = requests.post(URL, json={"telemetry": telemetry})
        if response.status_code == 200:
            data = response.json()
            data["_status"] = 200
            
            # Simple evidence check (soft validation)
            evidence = data.get("evidence", [])
            hallucination = False
            for ev in evidence:
                if ev.lower() not in telemetry.lower():
                    hallucination = True
            
            data["_hallucinated"] = hallucination
            results[name] = data
        else:
            results[name] = {"_status": response.status_code, "_error": response.text}
    except Exception as e:
        results[name] = {"_error": str(e)}

with open("test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("Done. Wrote to test_results.json.")

