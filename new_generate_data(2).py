#!/usr/bin/env python3
"""
Kubernetes SRE RCA synthetic SFT dataset generator.

Design goals:
- Standard-library only.
- Deterministic generation from a seed.
- 19 explicit root-cause classes with no generic fallback.
- Causal, topology-aware Kubernetes telemetry.
- Stateful five-timestep telemetry.
- Model-visible telemetry contains no internal generator labels.
- Scenario-specific semantic validation.
- Exact dataset-size enforcement.
- Semantic deduplication.
- UTF-8 JSONL output.
- SFT chat/messages format.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================================
# TAXONOMY / CONFIGURATION
# ============================================================================

ROOT_CAUSES = [
    "memory_exhaustion",
    "cpu_resource_exhaustion",
    "container_image_pull_failure",
    "scheduling_constraint",
    "database_connectivity",
    "dns_failure",
    "missing_secret",
    "configuration_error",
    "readiness_probe_failure",
    "liveness_probe_failure",
    "node_failure",
    "node_resource_pressure",
    "disk_pressure",
    "network_policy_block",
    "service_misconfiguration",
    "ingress_misconfiguration",
    "persistent_volume_failure",
    "resource_quota_exhaustion",
    "insufficient_evidence",
]

DIFFICULTIES = ("easy", "medium", "hard")

ENVIRONMENTS = (
    "production",
    "staging",
    "qa",
    "development",
)

NAMESPACES = (
    "payments",
    "orders",
    "catalog",
    "platform",
)

SERVICES = (
    "checkout-api",
    "orders-api",
    "catalog-api",
    "worker-api",
)

NORMAL_EVENT_REASONS = (
    "Scheduled",
    "Pulling",
    "Pulled",
    "Started",
)

SYSTEM_PROMPT = (
    "You are an expert Kubernetes Site Reliability Engineer. "
    "Analyze the supplied Kubernetes telemetry and return ONLY a JSON object "
    "with exactly these fields: failure, root_cause, confidence, evidence, "
    "severity, contributing_factors, causal_chain, alternative_hypotheses, "
    "remediation_actions. Base the diagnosis only on the supplied telemetry. "
    "Do not invent observations."
)

TIMELINE_OFFSETS = (-4, -3, -2, -1, 0)


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class K8sObject:
    kind: str
    name: str
    namespace: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    spec: Dict[str, Any] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogEntry:
    timestamp: str
    level: str
    pod: str
    container: str
    message: str


@dataclass
class EventEntry:
    timestamp: str
    type: str
    reason: str
    message: str
    source_component: str
    involved_object: Dict[str, str]


@dataclass
class MetricEntry:
    timestamp: str
    name: str
    labels: Dict[str, str]
    value: float


@dataclass
class GroundTruth:
    failure: str
    root_cause: str
    confidence: float
    evidence: List[str]
    severity: str
    contributing_factors: List[str]
    causal_chain: List[str]
    alternative_hypotheses: List[str]
    remediation_actions: List[str]


@dataclass
class ClusterState:
    environment: str
    timestamp: datetime
    objects: List[K8sObject] = field(default_factory=list)
    logs: List[LogEntry] = field(default_factory=list)
    events: List[EventEntry] = field(default_factory=list)
    metrics: List[MetricEntry] = field(default_factory=list)

    def objects_of_kind(self, kind: str) -> List[K8sObject]:
        return [x for x in self.objects if x.kind == kind]

    def get(self, kind: str, name: Optional[str] = None) -> Optional[K8sObject]:
        for obj in self.objects:
            if obj.kind == kind and (name is None or obj.name == name):
                return obj
        return None


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def objref(kind: str, name: str, namespace: str = "") -> Dict[str, str]:
    result = {"kind": kind, "name": name}
    if namespace:
        result["namespace"] = namespace
    return result


def random_id(rng: random.Random, length: int = 7) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(rng.choices(alphabet, k=length))


def deterministic_start(seed: int) -> datetime:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=seed % 50000)


def add_metric(
    state: ClusterState,
    offset: int,
    name: str,
    labels: Dict[str, str],
    value: float,
) -> None:
    state.metrics.append(
        MetricEntry(
            timestamp=iso(state.timestamp + timedelta(minutes=offset)),
            name=name,
            labels=labels,
            value=float(value),
        )
    )


def add_log(
    state: ClusterState,
    offset: int,
    pod: str,
    message: str,
    level: str = "INFO",
    container: str = "app",
) -> None:
    state.logs.append(
        LogEntry(
            timestamp=iso(state.timestamp + timedelta(minutes=offset)),
            level=level,
            pod=pod,
            container=container,
            message=message,
        )
    )


def add_event(
    state: ClusterState,
    offset: int,
    event_type: str,
    reason: str,
    message: str,
    involved: Dict[str, str],
    source: str = "kubelet",
) -> None:
    state.events.append(
        EventEntry(
            timestamp=iso(state.timestamp + timedelta(minutes=offset)),
            type=event_type,
            reason=reason,
            message=message,
            source_component=source,
            involved_object=involved,
        )
    )


def find_pod(state: ClusterState, index: int = 0) -> K8sObject:
    pods = state.objects_of_kind("Pod")
    if not pods:
        raise RuntimeError("Healthy cluster contains no Pods")
    return pods[index % len(pods)]


def container_status(pod: K8sObject) -> Dict[str, Any]:
    statuses = pod.status.get("containerStatuses", [])
    if not statuses:
        raise RuntimeError(f"Pod {pod.name} has no container status")
    return statuses[0]


def set_pod_state(
    pod: K8sObject,
    phase: str,
    ready: bool,
    state: Dict[str, Any],
    restart_count: int = 0,
    last_state: Optional[Dict[str, Any]] = None,
) -> None:
    pod.status["phase"] = phase
    pod.status["conditions"] = [
        {
            "type": "Ready",
            "status": "True" if ready else "False",
        }
    ]

    cs = container_status(pod)
    cs["ready"] = ready
    cs["state"] = state
    cs["restartCount"] = restart_count

    if last_state is None:
        cs.pop("lastState", None)
    else:
        cs["lastState"] = last_state


def metric_values(state: ClusterState, metric_name: str) -> List[float]:
    return [
        x.value
        for x in state.metrics
        if x.name == metric_name
    ]


def event_messages(state: ClusterState) -> List[str]:
    return [
        f"{x.reason}: {x.message}"
        for x in state.events
    ]


def has_event_text(state: ClusterState, text: str) -> bool:
    needle = text.lower()
    return any(
        needle in f"{e.reason} {e.message}".lower()
        for e in state.events
    )


def has_log_text(state: ClusterState, text: str) -> bool:
    needle = text.lower()
    return any(needle in x.message.lower() for x in state.logs)


def has_metric(state: ClusterState, name: str) -> bool:
    return any(x.name == name for x in state.metrics)


def severity_for(environment: str, blast_radius: str) -> str:
    if environment == "production" and blast_radius == "large":
        return "SEV-1"
    if environment in {"production", "staging"}:
        return "SEV-2"
    if blast_radius == "large":
        return "SEV-2"
    if blast_radius == "medium":
        return "SEV-3"
    return "SEV-4"


# ============================================================================
# HEALTHY BASELINE
# ============================================================================

def build_healthy_cluster(
    rng: random.Random,
    namespace: str,
    service_name: str,
    timestamp: datetime,
) -> ClusterState:
    environment = rng.choice(ENVIRONMENTS)
    state = ClusterState(
        environment=environment,
        timestamp=timestamp,
    )

    node_name = f"node-{random_id(rng)}"
    node_zone = rng.choice(("zone-a", "zone-b"))

    node = K8sObject(
        kind="Node",
        name=node_name,
        namespace="",
        labels={
            "kubernetes.io/hostname": node_name,
            "topology.kubernetes.io/zone": node_zone,
        },
        spec={
            "taints": [],
        },
        status={
            "conditions": [
                {"type": "Ready", "status": "True"},
                {"type": "MemoryPressure", "status": "False"},
                {"type": "DiskPressure", "status": "False"},
                {"type": "PIDPressure", "status": "False"},
            ],
            "allocatable": {
                "cpu": "4",
                "memory": "8Gi",
                "ephemeral-storage": "80Gi",
            },
            "capacity": {
                "cpu": "4",
                "memory": "8Gi",
                "ephemeral-storage": "80Gi",
            },
        },
    )
    state.objects.append(node)

    labels = {
        "app": service_name,
        "version": "v1",
    }

    pod_names: List[str] = []

    for _ in range(2):
        pod_name = f"{service_name}-{random_id(rng, 5)}"
        pod_names.append(pod_name)

        pod = K8sObject(
            kind="Pod",
            name=pod_name,
            namespace=namespace,
            labels=labels.copy(),
            spec={
                "nodeName": node_name,
                "containers": [
                    {
                        "name": "app",
                        "image": "registry.example/app:v1.4.2",
                        "ports": [
                            {
                                "name": "http",
                                "containerPort": 8080,
                                "protocol": "TCP",
                            }
                        ],
                        "resources": {
                            "requests": {
                                "cpu": "250m",
                                "memory": "256Mi",
                            },
                            "limits": {
                                "cpu": "1000m",
                                "memory": "512Mi",
                            },
                        },
                        "readinessProbe": {
                            "httpGet": {
                                "path": "/ready",
                                "port": 8080,
                            },
                            "periodSeconds": 10,
                        },
                        "livenessProbe": {
                            "httpGet": {
                                "path": "/health",
                                "port": 8080,
                            },
                            "periodSeconds": 10,
                        },
                    }
                ],
            },
            status={
                "phase": "Running",
                "conditions": [
                    {"type": "Ready", "status": "True"}
                ],
                "containerStatuses": [
                    {
                        "name": "app",
                        "ready": True,
                        "restartCount": 0,
                        "state": {
                            "running": {
                                "startedAt": iso(
                                    timestamp - timedelta(minutes=30)
                                )
                            }
                        },
                    }
                ],
            },
        )
        state.objects.append(pod)

    deployment = K8sObject(
        kind="Deployment",
        name=service_name,
        namespace=namespace,
        labels=labels.copy(),
        spec={
            "replicas": 2,
            "selector": {
                "matchLabels": labels.copy()
            },
            "template": {
                "metadata": {"labels": labels.copy()},
            },
        },
        status={
            "replicas": 2,
            "readyReplicas": 2,
            "availableReplicas": 2,
        },
    )

    replica_set = K8sObject(
        kind="ReplicaSet",
        name=f"{service_name}-{random_id(rng, 8)}",
        namespace=namespace,
        labels=labels.copy(),
        spec={
            "replicas": 2,
            "selector": {
                "matchLabels": labels.copy()
            },
        },
        status={
            "replicas": 2,
            "readyReplicas": 2,
        },
    )

    service = K8sObject(
        kind="Service",
        name=service_name,
        namespace=namespace,
        spec={
            "type": "ClusterIP",
            "selector": labels.copy(),
            "ports": [
                {
                    "name": "http",
                    "protocol": "TCP",
                    "port": 80,
                    "targetPort": 8080,
                }
            ],
        },
        status={
            "clusterIP": f"10.96.{rng.randint(10, 200)}.{rng.randint(10, 240)}"
        },
    )

    endpoints = K8sObject(
        kind="EndpointSlice",
        name=f"{service_name}-{random_id(rng, 5)}",
        namespace=namespace,
        labels={
            "kubernetes.io/service-name": service_name,
        },
        spec={
            "ports": [
                {
                    "name": "http",
                    "protocol": "TCP",
                    "port": 8080,
                }
            ],
            "endpoints": [
                {
                    "addresses": [f"10.0.0.{rng.randint(10, 99)}"],
                    "conditions": {"ready": True},
                },
                {
                    "addresses": [f"10.0.0.{rng.randint(100, 199)}"],
                    "conditions": {"ready": True},
                },
            ],
        },
    )

    state.objects.extend(
        [
            deployment,
            replica_set,
            service,
            endpoints,
        ]
    )

    return state


# ============================================================================
# BACKGROUND / NOISE
# ============================================================================

def add_background_telemetry(
    state: ClusterState,
    rng: random.Random,
) -> None:
    pods = state.objects_of_kind("Pod")

    for offset in TIMELINE_OFFSETS:
        pod = rng.choice(pods)

        add_metric(
            state,
            offset,
            "container_cpu_usage_ratio",
            {"pod": pod.name},
            rng.uniform(0.12, 0.31),
        )

        add_metric(
            state,
            offset,
            "container_memory_working_set_bytes",
            {"pod": pod.name},
            rng.randint(120, 230) * 1024 * 1024,
        )

        add_metric(
            state,
            offset,
            "http_requests_per_second",
            {"service": pod.labels["app"]},
            rng.uniform(65, 120),
        )

        if rng.random() < 0.85:
            add_log(
                state,
                offset,
                pod.name,
                (
                    f"request completed status=200 "
                    f"latency_ms={rng.randint(8, 42)}"
                ),
                "INFO",
            )

    add_event(
        state,
        -4,
        "Normal",
        "Scheduled",
        "Successfully assigned Pod to node",
        objref("Pod", pods[0].name, pods[0].namespace),
        "default-scheduler",
    )

    add_event(
        state,
        -4,
        "Normal",
        "Pulled",
        "Container image already present on node",
        objref("Pod", pods[0].name, pods[0].namespace),
        "kubelet",
    )

    add_event(
        state,
        -4,
        "Normal",
        "Started",
        "Started container",
        objref("Pod", pods[0].name, pods[0].namespace),
        "kubelet",
    )


# ============================================================================
# SCENARIO GENERATION
# ============================================================================

def generate_memory_exhaustion(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    limit_mib = rng.choice((384, 512, 640))
    start = rng.randint(210, 280)
    increments = rng.randint(45, 70)

    values = [
        start + increments * i
        for i in range(5)
    ]

    pod.spec["containers"][0]["resources"]["limits"]["memory"] = (
        f"{limit_mib}Mi"
    )

    for offset, value in zip(TIMELINE_OFFSETS, values):
        add_metric(
            state,
            offset,
            "container_memory_working_set_bytes",
            {"pod": pod.name},
            value * 1024 * 1024,
        )

    add_metric(
        state,
        0,
        "container_memory_limit_bytes",
        {"pod": pod.name},
        limit_mib * 1024 * 1024,
    )

    add_log(
        state,
        -1,
        pod.name,
        "allocation latency increased as resident memory continued to grow",
        "WARN",
    )
    add_log(
        state,
        0,
        pod.name,
        "process terminated while allocating memory",
        "ERROR",
    )

    set_pod_state(
        pod,
        "Running",
        False,
        {"waiting": {"reason": "CrashLoopBackOff"}},
        restart_count=rng.randint(2, 6),
        last_state={
            "terminated": {
                "reason": "OOMKilled",
                "exitCode": 137,
            }
        },
    )

    add_event(
        state,
        0,
        "Warning",
        "OOMKilling",
        "Container exceeded its memory cgroup limit",
        objref("Pod", pod.name, pod.namespace),
    )

    return GroundTruth(
        failure="Application container repeatedly restarts",
        root_cause="memory_exhaustion",
        confidence=0.97,
        evidence=[
            f"working-set memory rises from {values[0]}Mi to {values[-1]}Mi",
            f"container memory limit is {limit_mib}Mi",
            "last termination reason is OOMKilled with exit code 137",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "sustained memory growth",
            "container memory limit reached",
        ],
        causal_chain=[
            "working-set memory rises over successive samples",
            "memory approaches the configured container limit",
            "kernel terminates the process for memory exhaustion",
            "container enters a restart loop",
        ],
        alternative_hypotheses=[
            "node-wide memory pressure",
            "application crash unrelated to memory",
        ],
        remediation_actions=[
            "identify and fix the allocation growth",
            "inspect heap/profile data before changing limits",
            "increase the memory limit only if justified by workload requirements",
        ],
    )


def generate_cpu_exhaustion(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    service = state.get("Service", pod.labels["app"])

    base = rng.uniform(0.45, 0.65)
    values = [
        min(0.99, base + i * rng.uniform(0.07, 0.11))
        for i in range(5)
    ]

    for offset, value in zip(TIMELINE_OFFSETS, values):
        add_metric(
            state,
            offset,
            "container_cpu_usage_ratio",
            {"pod": pod.name},
            value,
        )
        add_metric(
            state,
            offset,
            "container_cpu_cfs_throttled_seconds_total",
            {"pod": pod.name},
            max(0.0, value - 0.55) * 3.0,
        )
        add_metric(
            state,
            offset,
            "http_request_latency_p95_ms",
            {"service": service.name},
            45 + value * 250,
        )

    add_log(
        state,
        0,
        pod.name,
        "request latency increased while application remained running",
        "WARN",
    )

    return GroundTruth(
        failure="Application latency rises while its container remains running",
        root_cause="cpu_resource_exhaustion",
        confidence=0.93,
        evidence=[
            "CPU usage approaches the configured container limit",
            "CPU throttling increases over the same interval",
            "request latency increases with CPU saturation",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "CPU limit constrains available compute",
        ],
        causal_chain=[
            "CPU demand increases",
            "CPU throttling increases",
            "application execution is delayed",
            "request latency rises",
        ],
        alternative_hypotheses=[
            "downstream dependency latency",
            "application lock contention",
        ],
        remediation_actions=[
            "profile the workload for CPU hotspots",
            "reduce avoidable CPU demand",
            "adjust CPU resources only after confirming the workload requirement",
        ],
    )


def generate_image_pull_failure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    bad_tag = rng.choice(
        ("release-does-not-exist", "v9.99.1", "missing-build")
    )
    image = f"registry.example/app:{bad_tag}"

    pod.spec["containers"][0]["image"] = image

    set_pod_state(
        pod,
        "Pending",
        False,
        {"waiting": {"reason": "ImagePullBackOff"}},
        restart_count=0,
    )

    add_event(
        state,
        -1,
        "Warning",
        "Failed",
        f'Failed to pull image "{image}": manifest unknown',
        objref("Pod", pod.name, pod.namespace),
    )

    add_event(
        state,
        0,
        "Warning",
        "BackOff",
        "Back-off pulling image",
        objref("Pod", pod.name, pod.namespace),
    )

    add_log(
        state,
        0,
        pod.name,
        "application container has not started",
        "WARN",
    )

    return GroundTruth(
        failure="Pod remains Pending because its container cannot start",
        root_cause="container_image_pull_failure",
        confidence=0.98,
        evidence=[
            f"container references image {image}",
            "kubelet reports manifest unknown",
            "container is Waiting with ImagePullBackOff",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "invalid image reference",
        ],
        causal_chain=[
            "Pod references an unavailable image",
            "registry rejects the image manifest request",
            "kubelet retries image retrieval",
            "container never starts",
        ],
        alternative_hypotheses=[
            "registry authentication failure",
            "temporary registry outage",
        ],
        remediation_actions=[
            "verify the image repository and tag",
            "verify registry availability and credentials if applicable",
            "roll out the corrected image reference",
        ],
    )


def generate_scheduling_constraint(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    node = state.get("Node")

    requested_cpu = rng.choice(("5", "6"))
    requested_memory = rng.choice(("10Gi", "12Gi"))

    pod.spec["nodeSelector"] = {
        "topology.kubernetes.io/zone": "zone-c",
    }
    pod.spec["containers"][0]["resources"]["requests"] = {
        "cpu": requested_cpu,
        "memory": requested_memory,
    }

    pod.status = {
        "phase": "Pending",
        "conditions": [
            {
                "type": "PodScheduled",
                "status": "False",
                "reason": "Unschedulable",
            }
        ],
        "containerStatuses": [],
    }

    zone = node.labels["topology.kubernetes.io/zone"]

    add_event(
        state,
        -1,
        "Warning",
        "FailedScheduling",
        "0/1 nodes available for requested Pod constraints",
        objref("Pod", pod.name, pod.namespace),
        "default-scheduler",
    )

    add_event(
        state,
        0,
        "Warning",
        "FailedScheduling",
        (
            f"0/1 nodes available: node selector requires zone-c "
            f"but available node is {zone}; requested CPU/memory exceed "
            f"node allocatable capacity"
        ),
        objref("Pod", pod.name, pod.namespace),
        "default-scheduler",
    )

    return GroundTruth(
        failure="Pod remains Pending and is never scheduled",
        root_cause="scheduling_constraint",
        confidence=0.97,
        evidence=[
            "PodScheduled is False with Unschedulable reason",
            f"Pod requires zone-c while the available node is in {zone}",
            "requested resources exceed the node's allocatable capacity",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "no available node satisfies the Pod constraints",
        ],
        causal_chain=[
            "scheduler evaluates node eligibility",
            "available node fails the Pod's selector and resource requirements",
            "scheduler cannot bind the Pod",
            "Pod remains Pending",
        ],
        alternative_hypotheses=[
            "temporary lack of capacity",
            "missing node pool",
        ],
        remediation_actions=[
            "inspect node labels and allocatable capacity",
            "correct the selector or resource request if incorrect",
            "provide a suitable node pool when the workload genuinely requires it",
        ],
    )


def generate_database_connectivity(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    app = find_pod(state)
    namespace = app.namespace

    db_pod = K8sObject(
        kind="Pod",
        name=f"orders-db-{random_id(rng, 5)}",
        namespace=namespace,
        labels={"app": "orders-db"},
        spec={
            "containers": [
                {
                    "name": "postgres",
                    "image": "postgres:16",
                    "ports": [{"containerPort": 5432}],
                }
            ],
        },
        status={
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "False"}],
            "containerStatuses": [
                {
                    "name": "postgres",
                    "ready": False,
                    "restartCount": 0,
                    "state": {"running": {}},
                }
            ],
        },
    )

    db_service = K8sObject(
        kind="Service",
        name="orders-db",
        namespace=namespace,
        spec={
            "selector": {"app": "orders-db"},
            "ports": [
                {
                    "port": 5432,
                    "targetPort": 5432,
                }
            ],
        },
        status={
            "clusterIP": "10.96.40.20",
        },
    )

    db_endpoints = K8sObject(
        kind="EndpointSlice",
        name=f"orders-db-{random_id(rng, 5)}",
        namespace=namespace,
        labels={"kubernetes.io/service-name": "orders-db"},
        spec={
            "ports": [{"port": 5432}],
            "endpoints": [],
        },
    )

    state.objects.extend(
        [
            db_pod,
            db_service,
            db_endpoints,
        ]
    )

    values = [3, 7, 15, 31, 52]

    for offset, value in zip(TIMELINE_OFFSETS, values):
        add_metric(
            state,
            offset,
            "db_connection_errors_total",
            {"service": "orders-db"},
            value,
        )

    add_log(
        state,
        -1,
        app.name,
        "database connection refused at 10.96.40.20:5432",
        "ERROR",
    )
    add_log(
        state,
        0,
        app.name,
        "database connection refused after retry",
        "ERROR",
    )

    add_event(
        state,
        0,
        "Warning",
        "Unhealthy",
        "readiness check cannot establish database connection",
        objref("Pod", app.name, namespace),
    )

    return GroundTruth(
        failure="Application cannot establish its database connection",
        root_cause="database_connectivity",
        confidence=0.95,
        evidence=[
            "database Pod is not Ready",
            "database EndpointSlice has no ready endpoints",
            "application connection attempts to the database Service are refused",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "database backend is unavailable",
        ],
        causal_chain=[
            "database workload loses readiness",
            "database Service has no usable endpoints",
            "application attempts to connect",
            "connections fail because no healthy database backend is available",
        ],
        alternative_hypotheses=[
            "NetworkPolicy blocking database traffic",
            "incorrect application connection configuration",
        ],
        remediation_actions=[
            "restore database backend health",
            "verify database endpoint readiness",
            "only then investigate application-side networking/configuration",
        ],
    )


def generate_dns_failure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    app = find_pod(state)

    resolver = K8sObject(
        kind="Pod",
        name=f"coredns-{random_id(rng, 5)}",
        namespace="kube-system",
        labels={"k8s-app": "kube-dns"},
        spec={
            "containers": [
                {
                    "name": "coredns",
                    "image": "coredns:1.11",
                }
            ]
        },
        status={
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "False"}],
            "containerStatuses": [
                {
                    "name": "coredns",
                    "ready": False,
                    "restartCount": 4,
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                    "lastState": {
                        "terminated": {
                            "reason": "Error",
                            "exitCode": 1,
                        }
                    },
                }
            ],
        },
    )

    state.objects.append(resolver)

    values = [2, 5, 11, 28, 47]

    for offset, value in zip(TIMELINE_OFFSETS, values):
        add_metric(
            state,
            offset,
            "coredns_dns_request_failures_total",
            {"pod": resolver.name},
            value,
        )

    add_log(
        state,
        -2,
        app.name,
        "lookup orders-api.orders.svc.cluster.local: i/o timeout",
        "ERROR",
    )
    add_log(
        state,
        0,
        app.name,
        "lookup catalog-api.orders.svc.cluster.local: i/o timeout",
        "ERROR",
    )
    add_log(
        state,
        -1,
        resolver.name,
        "DNS server failed to initialize one of its configured plugins",
        "ERROR",
        "coredns",
    )

    add_event(
        state,
        0,
        "Warning",
        "Unhealthy",
        "DNS resolver Pod is not Ready",
        objref("Pod", resolver.name, "kube-system"),
    )

    return GroundTruth(
        failure="Multiple in-cluster service lookups time out",
        root_cause="dns_failure",
        confidence=0.96,
        evidence=[
            "multiple workload Pods report DNS lookup timeouts",
            "the DNS resolver Pod is repeatedly restarting and not Ready",
            "DNS request failure metrics increase over time",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "resolver availability degraded",
        ],
        causal_chain=[
            "resolver health deteriorates",
            "resolver Pod becomes unavailable",
            "workloads issue service-name lookups",
            "DNS lookups time out",
        ],
        alternative_hypotheses=[
            "incorrect service name",
            "namespace resolution error",
        ],
        remediation_actions=[
            "restore resolver health",
            "inspect resolver configuration and logs",
            "verify DNS service/endpoints before changing application names",
        ],
    )


def generate_missing_secret(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    secret_name = f"{pod.labels['app']}-credentials"

    pod.spec["containers"][0]["envFrom"] = [
        {
            "secretRef": {
                "name": secret_name,
            }
        }
    ]

    set_pod_state(
        pod,
        "Pending",
        False,
        {"waiting": {"reason": "CreateContainerConfigError"}},
        restart_count=0,
    )

    add_event(
        state,
        0,
        "Warning",
        "Failed",
        f'secret "{secret_name}" not found',
        objref("Pod", pod.name, pod.namespace),
    )

    add_log(
        state,
        0,
        pod.name,
        "container configuration could not be created",
        "ERROR",
    )

    return GroundTruth(
        failure="Pod cannot create its application container",
        root_cause="missing_secret",
        confidence=0.98,
        evidence=[
            f"Pod references Secret {secret_name}",
            "kubelet reports the referenced Secret was not found",
            "container is Waiting with CreateContainerConfigError",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "required credential object is absent",
        ],
        causal_chain=[
            "Pod references a Secret",
            "referenced Secret cannot be found",
            "kubelet cannot construct the container environment",
            "container does not start",
        ],
        alternative_hypotheses=[
            "invalid container configuration",
            "RBAC access problem",
        ],
        remediation_actions=[
            "restore the required Secret",
            "verify required keys and namespace",
            "verify service-account permissions if the Secret exists",
        ],
    )


def generate_configuration_error(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    bad_value = rng.choice(
        (
            "not-a-number",
            "invalid",
            "tcp://:bad-port",
        )
    )

    pod.spec["containers"][0]["env"] = [
        {
            "name": "PORT",
            "value": bad_value,
        }
    ]

    set_pod_state(
        pod,
        "Running",
        False,
        {"waiting": {"reason": "CrashLoopBackOff"}},
        restart_count=4,
        last_state={
            "terminated": {
                "reason": "Error",
                "exitCode": 2,
            }
        },
    )

    add_log(
        state,
        -1,
        pod.name,
        f"startup configuration PORT value {bad_value!r} is invalid",
        "ERROR",
    )
    add_log(
        state,
        0,
        pod.name,
        "configuration validation failed; application exiting",
        "ERROR",
    )

    add_event(
        state,
        0,
        "Warning",
        "BackOff",
        "Back-off restarting failed container",
        objref("Pod", pod.name, pod.namespace),
    )

    return GroundTruth(
        failure="Application exits during startup configuration validation",
        root_cause="configuration_error",
        confidence=0.94,
        evidence=[
            f"container environment contains an invalid PORT value ({bad_value})",
            "startup logs reject the configuration",
            "container exits with code 2 and repeatedly restarts",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "invalid runtime configuration",
        ],
        causal_chain=[
            "application reads invalid startup configuration",
            "configuration validation fails",
            "process exits",
            "kubelet restarts the container",
        ],
        alternative_hypotheses=[
            "broken application image",
            "missing runtime dependency",
        ],
        remediation_actions=[
            "correct the configuration value",
            "validate configuration before rollout",
            "roll out the corrected configuration",
        ],
    )


def generate_probe_failure(
    state: ClusterState,
    rng: random.Random,
    root_cause: str,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    probe_name = (
        "readinessProbe"
        if root_cause == "readiness_probe_failure"
        else "livenessProbe"
    )

    pod.spec["containers"][0][probe_name] = {
        "httpGet": {
            "path": "/healthz",
            "port": 9999,
        },
        "periodSeconds": 10,
        "failureThreshold": 3,
    }

    if root_cause == "readiness_probe_failure":
        set_pod_state(
            pod,
            "Running",
            False,
            {"running": {}},
            restart_count=0,
        )

        for offset, value in zip(
            TIMELINE_OFFSETS,
            [1, 1, 1, 0, 0],
        ):
            add_metric(
                state,
                offset,
                "kube_pod_container_status_ready",
                {"pod": pod.name},
                value,
            )

        add_event(
            state,
            0,
            "Warning",
            "Unhealthy",
            "Readiness probe failed: connection refused",
            objref("Pod", pod.name, pod.namespace),
        )

        add_log(
            state,
            0,
            pod.name,
            "application process remains running and serving on port 8080",
            "INFO",
        )

        for endpoint in state.objects_of_kind("EndpointSlice"):
            if endpoint.namespace == pod.namespace:
                for item in endpoint.spec.get("endpoints", []):
                    item.setdefault("conditions", {})["ready"] = False

        return GroundTruth(
            failure="Pod remains running but is removed from ready traffic",
            root_cause=root_cause,
            confidence=0.95,
            evidence=[
                "readiness probe targets port 9999 while application exposes port 8080",
                "container remains Running with restartCount 0",
                "Ready condition is False",
                "kubelet reports readiness probe failure",
            ],
            severity=severity_for(state.environment, "medium"),
            contributing_factors=[
                "probe endpoint does not match the application listener",
            ],
            causal_chain=[
                "readiness probe targets an unavailable endpoint",
                "probe fails repeatedly",
                "Pod Ready condition becomes False",
                "Pod is removed from ready endpoints while process remains running",
            ],
            alternative_hypotheses=[
                "application startup delay",
                "application health endpoint failure",
            ],
            remediation_actions=[
                "correct the readiness probe endpoint or port",
                "verify the application listener before rollout",
            ],
        )

    set_pod_state(
        pod,
        "Running",
        False,
        {"waiting": {"reason": "CrashLoopBackOff"}},
        restart_count=5,
        last_state={
            "terminated": {
                "reason": "Error",
                "exitCode": 137,
            }
        },
    )

    add_event(
        state,
        0,
        "Warning",
        "Unhealthy",
        "Liveness probe failed: connection refused",
        objref("Pod", pod.name, pod.namespace),
    )

    add_log(
        state,
        0,
        pod.name,
        "health endpoint is unreachable on configured probe port",
        "ERROR",
    )

    return GroundTruth(
        failure="Container repeatedly restarts after liveness probe failures",
        root_cause=root_cause,
        confidence=0.95,
        evidence=[
            "liveness probe targets port 9999 while application exposes port 8080",
            "container has repeated restarts",
            "kubelet reports liveness probe failures followed by termination",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "liveness endpoint does not match the application listener",
        ],
        causal_chain=[
            "liveness probe targets an unavailable endpoint",
            "probe fails repeatedly",
            "kubelet terminates the container",
            "restart count increases",
        ],
        alternative_hypotheses=[
            "application crash",
            "application health endpoint failure",
        ],
        remediation_actions=[
            "correct the liveness probe endpoint or port",
            "verify health endpoint semantics",
            "avoid increasing failure thresholds without understanding the failure",
        ],
    )


def generate_node_failure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    node = state.get("Node")

    node.status["conditions"] = [
        {
            "type": "Ready",
            "status": "False",
            "reason": "KubeletNotReady",
        },
        {
            "type": "MemoryPressure",
            "status": "False",
        },
        {
            "type": "DiskPressure",
            "status": "False",
        },
        {
            "type": "PIDPressure",
            "status": "False",
        },
    ]

    set_pod_state(
        pod,
        "Unknown",
        False,
        {"waiting": {"reason": "ContainerStatusUnknown"}},
        restart_count=0,
    )

    for offset, value in zip(
        TIMELINE_OFFSETS,
        [5, 8, 12, 45, 180],
    ):
        add_metric(
            state,
            offset,
            "node_heartbeat_age_seconds",
            {"node": node.name},
            value,
        )

    add_event(
        state,
        0,
        "Warning",
        "NodeNotReady",
        "Node stopped reporting kubelet heartbeats",
        objref("Node", node.name),
        "node-controller",
    )

    add_event(
        state,
        0,
        "Warning",
        "NodeUnreachable",
        "Pod status is unknown because its node is unreachable",
        objref("Pod", pod.name, pod.namespace),
        "node-controller",
    )

    add_log(
        state,
        0,
        pod.name,
        "node heartbeat unavailable; container status cannot be refreshed",
        "WARN",
    )

    return GroundTruth(
        failure="Workload on one node becomes unreachable",
        root_cause="node_failure",
        confidence=0.97,
        evidence=[
            "Node Ready condition becomes False with KubeletNotReady",
            "node heartbeat age rises sharply",
            "node-controller reports the node is unreachable",
            "Pod status becomes Unknown",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "kubelet/node heartbeat lost",
        ],
        causal_chain=[
            "node stops reporting heartbeats",
            "control plane marks Node NotReady",
            "Pod status becomes unavailable",
            "workload on the node loses availability",
        ],
        alternative_hypotheses=[
            "single application process failure",
            "network path isolated from the control plane",
        ],
        remediation_actions=[
            "restore node or kubelet connectivity",
            "inspect node health and runtime",
            "verify workload rescheduling after node recovery",
        ],
    )


def generate_node_resource_pressure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    node = state.get("Node")

    node.status["conditions"][1] = {
        "type": "MemoryPressure",
        "status": "True",
        "reason": "KubeletHasInsufficientMemory",
    }

    values = [61, 69, 78, 89, 97]

    for offset, value in zip(TIMELINE_OFFSETS, values):
        add_metric(
            state,
            offset,
            "node_memory_utilization_percent",
            {"node": node.name},
            value,
        )

    set_pod_state(
        pod,
        "Failed",
        False,
        {"terminated": {"reason": "Evicted"}},
        restart_count=0,
    )

    add_event(
        state,
        0,
        "Warning",
        "NodeHasInsufficientMemory",
        "Node is under memory pressure",
        objref("Node", node.name),
    )

    add_event(
        state,
        0,
        "Warning",
        "Evicted",
        "Pod was evicted because the node was under memory pressure",
        objref("Pod", pod.name, pod.namespace),
    )

    add_log(
        state,
        0,
        pod.name,
        "workload terminated after node memory pressure increased",
        "WARN",
    )

    return GroundTruth(
        failure="Pod is evicted while node memory utilization becomes critical",
        root_cause="node_resource_pressure",
        confidence=0.97,
        evidence=[
            "node memory utilization rises from 61% to 97%",
            "Node MemoryPressure becomes True",
            "kubelet reports eviction due to node memory pressure",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "node-wide memory contention",
        ],
        causal_chain=[
            "node memory utilization rises",
            "node crosses its pressure threshold",
            "MemoryPressure becomes True",
            "kubelet evicts a workload",
        ],
        alternative_hypotheses=[
            "container-level OOM",
            "single workload memory leak",
        ],
        remediation_actions=[
            "identify node-wide memory consumers",
            "restore node memory headroom",
            "rebalance workloads if required",
        ],
    )


def generate_disk_pressure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)
    node = state.get("Node")

    node.status["conditions"][2] = {
        "type": "DiskPressure",
        "status": "True",
        "reason": "KubeletHasDiskPressure",
    }

    used_percent = [58, 67, 77, 89, 96]

    for offset, value in zip(TIMELINE_OFFSETS, used_percent):
        add_metric(
            state,
            offset,
            "node_filesystem_used_percent",
            {
                "node": node.name,
                "mountpoint": "/var/lib",
            },
            value,
        )

    set_pod_state(
        pod,
        "Failed",
        False,
        {"terminated": {"reason": "Evicted"}},
        restart_count=0,
    )

    add_event(
        state,
        0,
        "Warning",
        "NodeHasDiskPressure",
        "node filesystem available space is critically low",
        objref("Node", node.name),
    )

    add_event(
        state,
        0,
        "Warning",
        "Evicted",
        "Pod was evicted because of ephemeral-storage pressure",
        objref("Pod", pod.name, pod.namespace),
    )

    add_log(
        state,
        0,
        pod.name,
        "workload terminated after node filesystem pressure",
        "WARN",
    )

    return GroundTruth(
        failure="Pod is evicted while node filesystem capacity is exhausted",
        root_cause="disk_pressure",
        confidence=0.98,
        evidence=[
            "node filesystem usage rises from 58% to 96%",
            "Node DiskPressure becomes True",
            "kubelet reports eviction due to ephemeral-storage pressure",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "node filesystem consumption",
        ],
        causal_chain=[
            "filesystem consumption rises",
            "available node storage falls below the pressure threshold",
            "DiskPressure becomes True",
            "kubelet evicts workload",
        ],
        alternative_hypotheses=[
            "container memory exhaustion",
            "application crash",
        ],
        remediation_actions=[
            "identify large files, images, logs, and ephemeral-storage consumers",
            "safely restore filesystem headroom",
            "add capacity only after identifying the storage growth source",
        ],
    )


def generate_network_policy_block(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    app = find_pod(state)

    db = K8sObject(
        kind="Pod",
        name=f"orders-db-{random_id(rng, 5)}",
        namespace=app.namespace,
        labels={"app": "orders-db"},
        spec={
            "containers": [
                {
                    "name": "db",
                    "image": "postgres:16",
                    "ports": [{"containerPort": 5432}],
                }
            ],
        },
        status={
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [
                {
                    "name": "db",
                    "ready": True,
                    "restartCount": 0,
                    "state": {"running": {}},
                }
            ],
        },
    )

    policy = K8sObject(
        kind="NetworkPolicy",
        name="checkout-egress-policy",
        namespace=app.namespace,
        spec={
            "podSelector": {
                "matchLabels": {
                    "app": app.labels["app"],
                }
            },
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "podSelector": {
                                "matchLabels": {
                                    "app": "orders-db",
                                }
                            }
                        }
                    ],
                    "ports": [
                        {
                            "protocol": "TCP",
                            "port": 5432,
                        }
                    ],
                    "action": "Deny",
                }
            ],
        },
    )

    state.objects.extend([db, policy])

    for offset, value in zip(
        TIMELINE_OFFSETS,
        [0, 0, 1, 7, 19],
    ):
        add_metric(
            state,
            offset,
            "application_connection_timeout_total",
            {"pod": app.name},
            value,
        )

    add_log(
        state,
        0,
        app.name,
        "database connection attempt timed out",
        "ERROR",
    )

    add_log(
        state,
        0,
        db.name,
        "database process accepted local health checks normally",
        "INFO",
    )

    add_event(
        state,
        0,
        "Warning",
        "ConnectionTimeout",
        "connection attempt did not establish",
        objref("Pod", app.name, app.namespace),
        "application",
    )

    return GroundTruth(
        failure="Application cannot reach an otherwise healthy database backend",
        root_cause="network_policy_block",
        confidence=0.93,
        evidence=[
            "database Pod is Ready",
            "connection timeouts increase after the egress policy is active",
            "the applicable policy selects the application workload and restricts the database path",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "restrictive egress policy",
        ],
        causal_chain=[
            "database destination remains healthy",
            "application traffic matches the restrictive egress policy",
            "connection attempts do not establish",
            "application requests time out",
        ],
        alternative_hypotheses=[
            "database process unavailable",
            "service endpoint failure",
        ],
        remediation_actions=[
            "inspect the effective NetworkPolicy set",
            "permit only the required destination and port",
            "verify connectivity after the policy change",
        ],
    )


def generate_service_misconfiguration(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    service = state.objects_of_kind("Service")[0]
    endpoint = state.objects_of_kind("EndpointSlice")[0]
    pod = find_pod(state)

    service.spec["selector"] = {
        "app": service.name,
        "version": "v2",
    }

    endpoint.spec["endpoints"] = []

    add_metric(
        state,
        0,
        "service_endpoints_ready",
        {"service": service.name},
        0,
    )

    add_event(
        state,
        0,
        "Warning",
        "NoEndpoints",
        "Service has no endpoints matching its selector",
        objref("Service", service.name, service.namespace),
        "endpoint-controller",
    )

    add_log(
        state,
        0,
        pod.name,
        "requests to the Service ClusterIP have no backend",
        "ERROR",
    )

    return GroundTruth(
        failure="Service has no ready backend endpoints",
        root_cause="service_misconfiguration",
        confidence=0.97,
        evidence=[
            "Service selector requires version v2",
            "available Pods carry version v1",
            "EndpointSlice contains no ready endpoints",
        ],
        severity=severity_for(state.environment, "large"),
        contributing_factors=[
            "selector mismatch",
        ],
        causal_chain=[
            "Service selector changes",
            "available Pods no longer match the selector",
            "EndpointSlice becomes empty",
            "Service traffic has no backend",
        ],
        alternative_hypotheses=[
            "all application Pods are unhealthy",
            "temporary endpoint-controller delay",
        ],
        remediation_actions=[
            "restore the intended Service selector",
            "verify EndpointSlice population",
            "verify backend readiness after the correction",
        ],
    )


def generate_ingress_misconfiguration(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    service = state.objects_of_kind("Service")[0]
    pod = find_pod(state)

    ingress = K8sObject(
        kind="Ingress",
        name=f"{service.name}-public",
        namespace=service.namespace,
        spec={
            "rules": [
                {
                    "host": f"{service.name}.example.com",
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": service.name,
                                        "port": {
                                            "number": 81
                                        },
                                    }
                                },
                            }
                        ]
                    },
                }
            ]
        },
        status={
            "loadBalancer": {
                "ingress": [
                    {"ip": "203.0.113.10"}
                ]
            }
        },
    )

    state.objects.append(ingress)

    add_metric(
        state,
        0,
        "ingress_backend_5xx_total",
        {"ingress": ingress.name},
        27,
    )

    add_event(
        state,
        0,
        "Warning",
        "BackendNotFound",
        (
            f"Ingress backend references Service port 81, "
            f"but the Service exposes port {service.spec['ports'][0]['port']}"
        ),
        objref("Ingress", ingress.name, ingress.namespace),
        "ingress-controller",
    )

    add_log(
        state,
        0,
        pod.name,
        "client request reaches ingress but backend returns 503",
        "ERROR",
    )

    return GroundTruth(
        failure="Ingress returns 5xx because its backend port does not match the Service",
        root_cause="ingress_misconfiguration",
        confidence=0.96,
        evidence=[
            "Ingress backend references Service port 81",
            "Service exposes port 80",
            "ingress controller reports no matching backend port",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "backend port mismatch",
        ],
        causal_chain=[
            "Ingress references a Service port that does not exist",
            "ingress controller cannot construct the backend route",
            "requests reach the ingress layer",
            "backend requests return 5xx",
        ],
        alternative_hypotheses=[
            "backend application failure",
            "EndpointSlice failure",
        ],
        remediation_actions=[
            "correct the Ingress backend port",
            "verify Service and EndpointSlice relationships",
            "verify successful routing after rollout",
        ],
    )


def generate_persistent_volume_failure(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    storage_class = K8sObject(
        kind="StorageClass",
        name="fast",
        namespace="",
        spec={
            "provisioner": "example.csi.io",
        },
    )

    pvc = K8sObject(
        kind="PersistentVolumeClaim",
        name="orders-data",
        namespace=pod.namespace,
        spec={
            "storageClassName": "fast",
            "resources": {
                "requests": {
                    "storage": "20Gi",
                }
            },
        },
        status={
            "phase": "Pending",
        },
    )

    pv = K8sObject(
        kind="PersistentVolume",
        name="pv-orders",
        namespace="",
        spec={
            "storageClassName": "fast",
            "capacity": {
                "storage": "10Gi",
            },
            "claimRef": {
                "namespace": pod.namespace,
                "name": "orders-data",
            },
        },
        status={
            "phase": "Failed",
            "reason": "ProvisioningFailed",
        },
    )

    pod.spec["volumes"] = [
        {
            "name": "data",
            "persistentVolumeClaim": {
                "claimName": "orders-data",
            },
        }
    ]

    state.objects.extend(
        [
            storage_class,
            pvc,
            pv,
        ]
    )

    add_event(
        state,
        0,
        "Warning",
        "ProvisioningFailed",
        "requested 20Gi but available volume capacity is 10Gi",
        objref("PersistentVolumeClaim", pvc.name, pvc.namespace),
        "persistentvolume-controller",
    )

    add_log(
        state,
        0,
        pod.name,
        "application cannot mount required data volume",
        "ERROR",
    )

    return GroundTruth(
        failure="PersistentVolumeClaim remains Pending and workload cannot obtain storage",
        root_cause="persistent_volume_failure",
        confidence=0.97,
        evidence=[
            "PVC requests 20Gi from StorageClass fast",
            "available PV has only 10Gi and is Failed",
            "PVC remains Pending with a provisioning failure event",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "storage capacity mismatch",
        ],
        causal_chain=[
            "PVC requests storage capacity",
            "available volume cannot satisfy the request",
            "binding/provisioning fails",
            "workload cannot obtain the required volume",
        ],
        alternative_hypotheses=[
            "CSI controller outage",
            "StorageClass misconfiguration",
        ],
        remediation_actions=[
            "inspect StorageClass and CSI capacity",
            "provision a compatible volume",
            "verify PVC binding before restarting workloads",
        ],
    )


def generate_resource_quota_exhaustion(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    quota = K8sObject(
        kind="ResourceQuota",
        name="compute-quota",
        namespace=pod.namespace,
        spec={
            "hard": {
                "requests.cpu": "2",
                "requests.memory": "4Gi",
                "pods": "10",
            }
        },
        status={
            "hard": {
                "requests.cpu": "2",
                "requests.memory": "4Gi",
                "pods": "10",
            },
            "used": {
                "requests.cpu": "2",
                "requests.memory": "4Gi",
                "pods": "10",
            },
        },
    )

    attempted = K8sObject(
        kind="Pod",
        name=f"{pod.labels['app']}-pending-{random_id(rng, 5)}",
        namespace=pod.namespace,
        labels={
            "app": pod.labels["app"],
            "version": "v1",
        },
        spec={
            "containers": [
                {
                    "name": "app",
                    "image": "registry.example/app:v1.4.2",
                    "resources": {
                        "requests": {
                            "cpu": "500m",
                            "memory": "512Mi",
                        }
                    },
                    "ports": pod.spec["containers"][0].get("ports", []),
                }
            ]
        },
        status={
            "phase": "Pending",
            "conditions": [
                {
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                }
            ],
            "containerStatuses": [],
        },
    )

    state.objects.append(quota)
    state.objects.append(attempted)

    add_event(
        state,
        0,
        "Warning",
        "FailedCreate",
        "exceeded quota: compute-quota; requested requests.cpu exceeds remaining quota",
        objref("Pod", attempted.name, attempted.namespace),
        "resourcequota-controller",
    )

    add_log(
        state,
        0,
        attempted.name,
        "workload creation rejected by namespace resource policy",
        "WARN",
    )

    return GroundTruth(
        failure="Requested workload is rejected because namespace quota is exhausted",
        root_cause="resource_quota_exhaustion",
        confidence=0.98,
        evidence=[
            "ResourceQuota CPU usage equals its hard CPU limit",
            "new workload requests additional CPU",
            "admission reports the quota is exceeded",
        ],
        severity=severity_for(state.environment, "medium"),
        contributing_factors=[
            "namespace resource quota exhausted",
        ],
        causal_chain=[
            "namespace quota reaches its hard limit",
            "new workload requests additional resources",
            "admission rejects the request",
            "new Pod is not admitted for normal scheduling",
        ],
        alternative_hypotheses=[
            "node capacity shortage",
            "scheduler constraints",
        ],
        remediation_actions=[
            "inspect namespace quota usage",
            "remove unnecessary resource consumption",
            "increase quota only when justified by capacity and policy",
        ],
    )


def generate_insufficient_evidence(
    state: ClusterState,
    rng: random.Random,
    difficulty: str,
) -> GroundTruth:
    pod = find_pod(state)

    for offset, value in zip(
        TIMELINE_OFFSETS,
        [700, 1000, 1300, 1700, 2100],
    ):
        add_metric(
            state,
            offset,
            "http_request_latency_p95_ms",
            {"service": pod.labels["app"]},
            value,
        )

    add_log(
        state,
        -1,
        pod.name,
        "upstream request timed out after 2 seconds",
        "ERROR",
    )

    add_log(
        state,
        0,
        pod.name,
        "retry attempt timed out",
        "ERROR",
    )

    return GroundTruth(
        failure="Requests are timing out but available telemetry cannot isolate the failing dependency",
        root_cause="insufficient_evidence",
        confidence=0.34,
        evidence=[
            "application timeouts are observed",
            "Pod is Running and Ready",
            "Service and EndpointSlice appear healthy",
            "no dependency-level failure telemetry is available",
        ],
        severity=severity_for(state.environment, "small"),
        contributing_factors=[
            "missing downstream telemetry",
        ],
        causal_chain=[
            "request latency increases",
            "application reports dependency timeout",
            "available telemetry confirms only the symptom",
            "the failing dependency cannot be isolated from the evidence supplied",
        ],
        alternative_hypotheses=[
            "database connectivity",
            "network path failure",
            "downstream service latency",
        ],
        remediation_actions=[
            "collect downstream service telemetry",
            "collect DNS and network telemetry",
            "inspect dependency-level latency and errors before changing configuration",
        ],
    )


# ============================================================================
# SCENARIO DISPATCH
# ============================================================================

def generate_scenario(
    state: ClusterState,
    rng: random.Random,
    root_cause: str,
    difficulty: str,
) -> GroundTruth:
    generators = {
        "memory_exhaustion": generate_memory_exhaustion,
        "cpu_resource_exhaustion": generate_cpu_exhaustion,
        "container_image_pull_failure": generate_image_pull_failure,
        "scheduling_constraint": generate_scheduling_constraint,
        "database_connectivity": generate_database_connectivity,
        "dns_failure": generate_dns_failure,
        "missing_secret": generate_missing_secret,
        "configuration_error": generate_configuration_error,
        "node_failure": generate_node_failure,
        "node_resource_pressure": generate_node_resource_pressure,
        "disk_pressure": generate_disk_pressure,
        "network_policy_block": generate_network_policy_block,
        "service_misconfiguration": generate_service_misconfiguration,
        "ingress_misconfiguration": generate_ingress_misconfiguration,
        "persistent_volume_failure": generate_persistent_volume_failure,
        "resource_quota_exhaustion": generate_resource_quota_exhaustion,
        "insufficient_evidence": generate_insufficient_evidence,
    }

    if root_cause in generators:
        return generators[root_cause](state, rng, difficulty)

    if root_cause in {
        "readiness_probe_failure",
        "liveness_probe_failure",
    }:
        return generate_probe_failure(
            state,
            rng,
            root_cause,
            difficulty,
        )

    raise RuntimeError(
        f"No dedicated scenario generator exists for root cause: {root_cause}"
    )


# ============================================================================
# TELEMETRY SERIALIZATION
# ============================================================================

def serialize_state(state: ClusterState) -> Dict[str, Any]:
    return {
        "cluster_state": {
            "environment": state.environment,
            "objects": [
                asdict(x)
                for x in state.objects
            ],
        },
        "metrics": [
            asdict(x)
            for x in sorted(
                state.metrics,
                key=lambda x: parse_iso(x.timestamp),
            )
        ],
        "logs": [
            asdict(x)
            for x in sorted(
                state.logs,
                key=lambda x: parse_iso(x.timestamp),
            )
        ],
        "events": [
            asdict(x)
            for x in sorted(
                state.events,
                key=lambda x: parse_iso(x.timestamp),
            )
        ],
    }


# ============================================================================
# ANTI-LEAKAGE
# ============================================================================

def leakage_detected(
    telemetry: Dict[str, Any],
    root_cause: str,
) -> bool:
    text = json.dumps(
        telemetry,
        ensure_ascii=False,
        sort_keys=True,
    ).lower()

    forbidden = {
        "simulated fault",
        "fault injected",
        "ground truth",
        "hidden root cause",
        "generator",
        "scenario id",
        "scenario_id",
    }

    if any(term in text for term in forbidden):
        return True

    normalized_root = root_cause.lower()
    human_root = normalized_root.replace("_", " ")

    if normalized_root in text:
        return True

    if human_root in text:
        return True

    return False


# ============================================================================
# STRUCTURAL VALIDATION
# ============================================================================

def validate_timestamps(telemetry: Dict[str, Any]) -> bool:
    for key in ("metrics", "logs", "events"):
        values = telemetry.get(key, [])
        timestamps = []

        for item in values:
            timestamp = item.get("timestamp")
            if not isinstance(timestamp, str):
                return False

            try:
                timestamps.append(parse_iso(timestamp))
            except ValueError:
                return False

        if timestamps != sorted(timestamps):
            return False

    return True


def validate_causal_ordering(telemetry: Dict[str, Any]) -> bool:
    metrics = telemetry.get("metrics", [])
    events = telemetry.get("events", [])
    logs = telemetry.get("logs", [])
    
    # Get the earliest metric timestamp and latest failure event 
    # Must ensure metrics are logged leading up to or concurrently with the failure event
    if not metrics or not events:
        return True
        
    first_metric = min(parse_iso(m["timestamp"]) for m in metrics)
    last_event = max(parse_iso(e["timestamp"]) for e in events)
    
    if first_metric > last_event:
        return False
        
    return True


def validate_pod_states(
    telemetry: Dict[str, Any],
    root_cause: str,
) -> bool:
    objects = telemetry["cluster_state"]["objects"]
    pods = [
        x for x in objects
        if x["kind"] == "Pod"
    ]

    nodes = {
        x["name"]
        for x in objects
        if x["kind"] == "Node"
    }

    for pod in pods:
        status = pod.get("status", {})
        phase = status.get("phase")
        statuses = status.get("containerStatuses", [])

        if phase == "Pending":
            for container in statuses:
                if "running" in container.get("state", {}):
                    return False

        if phase == "Running" and root_cause != "scheduling_constraint":
            if not statuses:
                return False

        ready_conditions = [
            x
            for x in status.get("conditions", [])
            if x.get("type") == "Ready"
        ]

        if ready_conditions:
            ready = ready_conditions[0].get("status") == "True"
            container_ready = any(
                x.get("ready") is True
                for x in statuses
            )

            if ready != container_ready:
                return False

        for container in statuses:
            waiting = container.get("state", {}).get("waiting", {})
            restart_count = container.get("restartCount", 0)

            if (
                waiting.get("reason") == "CrashLoopBackOff"
                and restart_count < 1
            ):
                return False

            terminated = (
                container
                .get("lastState", {})
                .get("terminated", {})
            )

            if (
                terminated.get("reason") == "OOMKilled"
                and terminated.get("exitCode") != 137
            ):
                return False

        node_name = pod.get("spec", {}).get("nodeName")

        if (
            node_name
            and node_name not in nodes
            and phase not in {"Pending"}
        ):
            return False

    return True


def validate_topology(telemetry: Dict[str, Any]) -> bool:
    objects = telemetry["cluster_state"]["objects"]

    pods = [
        x for x in objects
        if x["kind"] == "Pod"
    ]

    services = [
        x for x in objects
        if x["kind"] == "Service"
    ]

    endpoints = [
        x for x in objects
        if x["kind"] == "EndpointSlice"
    ]

    for service in services:
        selector = service.get("spec", {}).get("selector", {})

        if not isinstance(selector, dict):
            return False

        matching_pods = []

        for pod in pods:
            if pod["namespace"] != service["namespace"]:
                continue

            labels = pod.get("labels", {})

            if all(
                labels.get(k) == v
                for k, v in selector.items()
            ):
                matching_pods.append(pod)

        service_port_list = service.get("spec", {}).get("ports", [])

        for service_port in service_port_list:
            target_port = service_port.get("targetPort")

            if isinstance(target_port, int):
                for pod in matching_pods:
                    containers = pod.get("spec", {}).get("containers", [])

                    exposed = any(
                        any(
                            port.get("containerPort") == target_port
                            for port in c.get("ports", [])
                        )
                        for c in containers
                    )

                    if not exposed:
                        return False

    for endpoint in endpoints:
        endpoint_list = endpoint.get("spec", {}).get("endpoints", [])

        for item in endpoint_list:
            conditions = item.get("conditions", {})

            if not isinstance(conditions, dict):
                return False

    return True


# ============================================================================
# SCENARIO-SPECIFIC VALIDATION
# ============================================================================

def validate_specific(
    state: ClusterState,
    truth: GroundTruth,
) -> bool:
    root = truth.root_cause

    objects = state.objects
    pods = state.objects_of_kind("Pod")
    nodes = state.objects_of_kind("Node")

    if not pods:
        return False

    if root == "memory_exhaustion":
        pod = pods[0]
        cs = container_status(pod)
        terminated = cs.get("lastState", {}).get("terminated", {})

        return (
            has_metric(state, "container_memory_working_set_bytes")
            and has_metric(state, "container_memory_limit_bytes")
            and terminated.get("reason") == "OOMKilled"
            and terminated.get("exitCode") == 137
            and cs.get("restartCount", 0) > 0
            and len(metric_values(
                state,
                "container_memory_working_set_bytes",
            )) >= 5
        )

    if root == "cpu_resource_exhaustion":
        values = metric_values(
            state,
            "container_cpu_usage_ratio",
        )

        throttled = metric_values(
            state,
            "container_cpu_cfs_throttled_seconds_total",
        )

        latency = metric_values(
            state,
            "http_request_latency_p95_ms",
        )

        return (
            len(values) >= 5
            and values[-1] > values[0]
            and len(throttled) >= 5
            and throttled[-1] >= throttled[0]
            and len(latency) >= 5
            and latency[-1] > latency[0]
        )

    if root == "container_image_pull_failure":
        pod = pods[0]
        cs = container_status(pod)

        return (
            pod.status["phase"] == "Pending"
            and cs.get("state", {}).get("waiting", {}).get("reason")
            == "ImagePullBackOff"
            and has_event_text(state, "manifest unknown")
        )

    if root == "scheduling_constraint":
        pod = pods[0]

        return (
            pod.status["phase"] == "Pending"
            and pod.status["conditions"][0].get("status") == "False"
            and pod.status["conditions"][0].get("reason")
            == "Unschedulable"
            and has_event_text(state, "zone-c")
        )

    if root == "database_connectivity":
        db_pods = [
            x
            for x in pods
            if x.name.startswith("orders-db-")
        ]

        db_endpoints = [
            x
            for x in objects
            if (
                x.kind == "EndpointSlice"
                and x.name.startswith("orders-db-")
            )
        ]

        if not db_pods or not db_endpoints:
            return False

        db_status = db_pods[0].status

        return (
            db_status["conditions"][0]["status"] == "False"
            and not db_endpoints[0].spec["endpoints"]
            and has_log_text(state, "connection refused")
        )

    if root == "dns_failure":
        resolver_pods = [
            x
            for x in pods
            if x.namespace == "kube-system"
        ]

        if not resolver_pods:
            return False

        resolver = resolver_pods[0]

        return (
            resolver.status["conditions"][0]["status"] == "False"
            and container_status(resolver)["restartCount"] > 0
            and has_metric(
                state,
                "coredns_dns_request_failures_total",
            )
            and has_log_text(state, "lookup")
        )

    if root == "missing_secret":
        pod = pods[0]
        env_from = (
            pod.spec["containers"][0]
            .get("envFrom", [])
        )

        referenced = any(
            "secretRef" in x
            for x in env_from
        )

        return (
            referenced
            and container_status(pod)
            .get("state", {})
            .get("waiting", {})
            .get("reason")
            == "CreateContainerConfigError"
            and has_event_text(state, "not found")
        )

    if root == "configuration_error":
        pod = pods[0]
        env = pod.spec["containers"][0].get("env", [])

        invalid_port = any(
            x.get("name") == "PORT"
            and x.get("value") in {
                "not-a-number",
                "invalid",
                "tcp://:bad-port",
            }
            for x in env
        )

        cs = container_status(pod)

        return (
            invalid_port
            and cs.get("restartCount", 0) > 0
            and cs.get("lastState", {})
            .get("terminated", {})
            .get("exitCode") == 2
            and has_log_text(state, "configuration")
        )

    if root == "readiness_probe_failure":
        pod = pods[0]
        cs = container_status(pod)

        return (
            pod.status["phase"] == "Running"
            and pod.status["conditions"][0]["status"] == "False"
            and cs["ready"] is False
            and cs["restartCount"] == 0
            and "readinessProbe" in pod.spec["containers"][0]
            and has_event_text(state, "Readiness")
        )

    if root == "liveness_probe_failure":
        pod = pods[0]
        cs = container_status(pod)

        return (
            cs["restartCount"] > 0
            and cs.get("state", {})
            .get("waiting", {})
            .get("reason")
            == "CrashLoopBackOff"
            and "livenessProbe" in pod.spec["containers"][0]
            and has_event_text(state, "Liveness")
        )

    if root == "node_failure":
        if not nodes:
            return False

        node = nodes[0]

        ready = next(
            (
                x
                for x in node.status["conditions"]
                if x["type"] == "Ready"
            ),
            None,
        )

        return (
            ready is not None
            and ready["status"] == "False"
            and has_metric(
                state,
                "node_heartbeat_age_seconds",
            )
            and has_event_text(state, "NodeNotReady")
        )

    if root == "node_resource_pressure":
        if not nodes:
            return False

        node = nodes[0]

        pressure = next(
            (
                x
                for x in node.status["conditions"]
                if x["type"] == "MemoryPressure"
            ),
            None,
        )

        return (
            pressure is not None
            and pressure["status"] == "True"
            and has_metric(
                state,
                "node_memory_utilization_percent",
            )
            and has_event_text(state, "evicted")
        )

    if root == "disk_pressure":
        if not nodes:
            return False

        node = nodes[0]

        pressure = next(
            (
                x
                for x in node.status["conditions"]
                if x["type"] == "DiskPressure"
            ),
            None,
        )

        return (
            pressure is not None
            and pressure["status"] == "True"
            and has_metric(
                state,
                "node_filesystem_used_percent",
            )
            and has_event_text(state, "evicted")
        )

    if root == "network_policy_block":
        policies = state.objects_of_kind("NetworkPolicy")
        db_pods = [
            x
            for x in state.objects_of_kind("Pod")
            if x.labels.get("app") == "orders-db"
        ]

        return (
            bool(policies)
            and bool(db_pods)
            and container_status(db_pods[0]).get("ready") is True
            and has_metric(
                state,
                "application_connection_timeout_total",
            )
            and has_log_text(state, "timed out")
        )

    if root == "service_misconfiguration":
        services = state.objects_of_kind("Service")
        slices = state.objects_of_kind("EndpointSlice")

        if not services or not slices:
            return False

        service = services[0]
        endpoint = slices[0]

        return (
            service.spec["selector"].get("version") == "v2"
            and not endpoint.spec["endpoints"]
            and has_event_text(state, "NoEndpoints")
        )

    if root == "ingress_misconfiguration":
        ingresses = state.objects_of_kind("Ingress")
        services = state.objects_of_kind("Service")

        if not ingresses or not services:
            return False

        ingress_port = (
            ingresses[0].spec["rules"][0]["http"]["paths"][0]
            ["backend"]["service"]["port"]["number"]
        )

        service_port = services[0].spec["ports"][0]["port"]

        return (
            ingress_port != service_port
            and has_event_text(state, "backend")
            and has_metric(
                state,
                "ingress_backend_5xx_total",
            )
        )

    if root == "persistent_volume_failure":
        pvcs = state.objects_of_kind("PersistentVolumeClaim")
        pvs = state.objects_of_kind("PersistentVolume")

        if not pvcs or not pvs:
            return False

        return (
            pvcs[0].status["phase"] == "Pending"
            and pvs[0].status["phase"] == "Failed"
            and has_event_text(state, "20Gi")
        )

    if root == "resource_quota_exhaustion":
        quotas = state.objects_of_kind("ResourceQuota")

        if not quotas:
            return False

        quota = quotas[0]

        return (
            quota.status["used"]["requests.cpu"]
            == quota.status["hard"]["requests.cpu"]
            and has_event_text(state, "exceeded quota")
        )

    if root == "insufficient_evidence":
        return (
            truth.confidence < 0.5
            and len(truth.alternative_hypotheses) >= 3
            and has_log_text(state, "timed out")
            and len(metric_values(
                state,
                "http_request_latency_p95_ms",
            )) >= 5
        )

    return False


# ============================================================================
# FULL VALIDATION
# ============================================================================

def validate_ground_truth(truth: GroundTruth) -> bool:
    if truth.root_cause not in ROOT_CAUSES:
        return False

    if not truth.failure.strip():
        return False

    if not 0.0 <= truth.confidence <= 1.0:
        return False

    if not truth.evidence:
        return False

    if not truth.causal_chain:
        return False

    if not truth.remediation_actions:
        return False

    if truth.root_cause == "insufficient_evidence":
        if truth.confidence >= 0.5:
            return False

    else:
        if truth.confidence < 0.5:
            return False

    dangerous = (
        "delete all",
        "disable networkpolicy",
        "disable network policy",
        "remove all limits",
        "restart everything",
        "rm -rf",
        "delete production",
    )

    remediation_text = " ".join(
        truth.remediation_actions
    ).lower()

    if any(x in remediation_text for x in dangerous):
        return False

    return True


def validate_record(
    telemetry: Dict[str, Any],
    truth: GroundTruth,
) -> bool:
    if leakage_detected(
        telemetry,
        truth.root_cause,
    ):
        return False

    if not validate_ground_truth(truth):
        return False

    if not validate_timestamps(telemetry):
        return False

    if not validate_causal_ordering(telemetry):
        return False

    if not validate_pod_states(
        telemetry,
        truth.root_cause,
    ):
        return False

    if not validate_topology(telemetry):
        return False

    state = ClusterState(
        environment=telemetry["cluster_state"]["environment"],
        timestamp=datetime.now(timezone.utc),
        objects=[
            K8sObject(**x)
            for x in telemetry["cluster_state"]["objects"]
        ],
        metrics=[
            MetricEntry(**x)
            for x in telemetry["metrics"]
        ],
        logs=[
            LogEntry(**x)
            for x in telemetry["logs"]
        ],
        events=[
            EventEntry(**x)
            for x in telemetry["events"]
        ],
    )

    if not validate_specific(state, truth):
        return False

    return True


# ============================================================================
# SEMANTIC DEDUPLICATION
# ============================================================================

def normalized_object_signature(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Names and random identifiers are deliberately removed.

    Namespace/environment are retained because they are meaningful
    contextual dimensions, while object identity is not.
    """
    return {
        "kind": obj.get("kind"),
        "namespace": obj.get("namespace"),
        "labels": obj.get("labels"),
        "spec": obj.get("spec"),
        "status": obj.get("status"),
    }


def semantic_signature(
    telemetry: Dict[str, Any],
    truth: GroundTruth,
    difficulty: str,
) -> str:
    objects = [
        normalized_object_signature(x)
        for x in telemetry["cluster_state"]["objects"]
    ]

    metrics = []

    for item in telemetry["metrics"]:
        value = item["value"]

        if value == 0:
            bucket = "zero"
        elif value < 1:
            bucket = "fraction-low"
        elif value < 10:
            bucket = "low"
        elif value < 100:
            bucket = "medium"
        elif value < 1000:
            bucket = "high"
        elif value < 10_000_000:
            bucket = "very-high"
        else:
            bucket = "bytes-high"

        metrics.append(
            (
                item["name"],
                item["labels"],
                bucket,
            )
        )

    payload = {
        "root_cause": truth.root_cause,
        "difficulty": difficulty,
        "environment": telemetry["cluster_state"]["environment"],
        "objects": sorted(
            objects,
            key=lambda x: (
                x.get("kind", ""),
                x.get("namespace", ""),
                json.dumps(
                    x.get("spec", {}),
                    sort_keys=True,
                ),
            ),
        ),
        "metrics": sorted(
            metrics,
            key=lambda x: (
                x[0],
                json.dumps(
                    x[1],
                    sort_keys=True,
                ),
                x[2],
            ),
        ),
    }

    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================================
# DATASET RECORD
# ============================================================================

def make_record(
    state: ClusterState,
    truth: GroundTruth,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    telemetry = serialize_state(state)

    telemetry_json = json.dumps(
        telemetry,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    user_content = (
        "Analyze this Kubernetes telemetry and determine the most defensible "
        "root cause. Use only the observations supplied. Distinguish the "
        "primary diagnosis from plausible alternatives.\n\n"
        + telemetry_json
    )

    record = {
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_content,
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    asdict(truth),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
    }

    return record, telemetry


# ============================================================================
# DATASET GENERATION
# ============================================================================

def choose_root_cause(
    rng: random.Random,
    generated_count: int,
    attempts: int,
) -> str:
    """
    Force deterministic round-robin coverage while still randomizing
    the starting offset, but increment by attempts so a failing class
    doesn't block the increment cycle.
    """
    start = rng.randrange(len(ROOT_CAUSES))
    return ROOT_CAUSES[
        (start + attempts) % len(ROOT_CAUSES)
    ]


def generate_dataset(
    num_samples: int,
    seed: int,
    max_attempts_multiplier: int = 100,
) -> List[Dict[str, Any]]:
    if num_samples <= 0:
        raise ValueError("num_samples must be greater than zero")

    rng = random.Random(seed)

    records: List[Dict[str, Any]] = []
    seen: set[str] = set()

    attempts = 0
    max_attempts = max(
        num_samples * max_attempts_multiplier,
        5000,
    )

    while len(records) < num_samples:
        attempts += 1

        if attempts > max_attempts:
            raise RuntimeError(
                "Unable to generate the requested number of valid, "
                f"unique records. Requested={num_samples}, "
                f"generated={len(records)}, attempts={attempts}."
            )

        root_cause = choose_root_cause(
            rng,
            len(records),
            attempts,
        )

        difficulty = rng.choice(DIFFICULTIES)
        namespace = rng.choice(NAMESPACES)
        service = rng.choice(SERVICES)

        timestamp = (
            deterministic_start(seed)
            + timedelta(
                minutes=rng.randint(0, 50_000)
            )
        )

        state = build_healthy_cluster(
            rng,
            namespace,
            service,
            timestamp,
        )

        truth = generate_scenario(
            state,
            rng,
            root_cause,
            difficulty,
        )

        record, telemetry = make_record(
            state,
            truth,
        )

        signature = semantic_signature(
            telemetry,
            truth,
            difficulty,
        )

        if signature in seen:
            continue

        if not validate_record(
            telemetry,
            truth,
        ):
            continue

        seen.add(signature)
        records.append(record)

    if len(records) != num_samples:
        raise RuntimeError(
            f"Exact-size invariant violated: "
            f"{len(records)} != {num_samples}"
        )

    return records


# ============================================================================
# POST-GENERATION AUDIT
# ============================================================================

def audit_dataset(
    records: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    counts = {
        root: 0
        for root in ROOT_CAUSES
    }

    duplicates = 0
    invalid_json = 0
    leakage_count = 0

    seen_hashes: set[str] = set()

    for record in records:
        messages = record["messages"]
        user = next(
            x["content"]
            for x in messages
            if x["role"] == "user"
        )
        assistant = next(
            x["content"]
            for x in messages
            if x["role"] == "assistant"
        )

        telemetry_json = user.split(
            "\n\n",
            1,
        )[1]

        telemetry = json.loads(
            telemetry_json
        )

        truth_dict = json.loads(
            assistant
        )

        root = truth_dict["root_cause"]

        if root in counts:
            counts[root] += 1

        digest = hashlib.sha256(
            json.dumps(
                telemetry,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        if digest in seen_hashes:
            duplicates += 1

        seen_hashes.add(digest)

        if leakage_detected(
            telemetry,
            root,
        ):
            leakage_count += 1

    return {
        "records": len(records),
        "root_cause_counts": counts,
        "missing_root_causes": [
            x
            for x, count in counts.items()
            if count == 0
        ],
        "duplicate_telemetry": duplicates,
        "invalid_records": invalid_json,
        "leakage_records": leakage_count,
    }


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Kubernetes RCA SFT JSONL data."
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=350,
        help="Exact number of records to generate.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic RNG seed.",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="train.jsonl",
        help="Output JSONL file.",
    )

    args = parser.parse_args()

    records = generate_dataset(
        num_samples=args.samples,
        seed=args.seed,
    )

    audit = audit_dataset(records)

    if audit["records"] != args.samples:
        raise RuntimeError(
            f"Audit record count mismatch: "
            f"{audit['records']} != {args.samples}"
        )

    if audit["invalid_records"] != 0:
        raise RuntimeError(
            f"Audit found {audit['invalid_records']} invalid records."
        )

    if audit["duplicate_telemetry"] != 0:
        raise RuntimeError(
            f"Audit found {audit['duplicate_telemetry']} duplicates."
        )

    if audit["leakage_records"] != 0:
        raise RuntimeError(
            f"Audit found {audit['leakage_records']} leakage records."
        )

    if audit["missing_root_causes"]:
        raise RuntimeError(
            "Missing root-cause classes: "
            + ", ".join(audit["missing_root_causes"])
        )

    with open(
        args.output,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output:
        for record in records:
            output.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    print(
        json.dumps(
            {
                "status": "VALIDATION_PASSED",
                "output": args.output,
                "records": audit["records"],
                "root_causes": audit["root_cause_counts"],
                "duplicates": audit["duplicate_telemetry"],
                "leakage": audit["leakage_records"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()