import asyncio
import os
import time
import httpx
import structlog
from difflib import SequenceMatcher
from typing import Dict, List

# RAE-Suite: Tactical Semantic Watchdog v2.3 (HIVE-CIRCUIT-BREAKER v1.0 compliant)
# Implements:
# A. Semantic Loop Detection (Anti-Echo: >= 3 rejections OR semantic similarity > 0.90 -> BLOCKED_LOOP)
# B. Heartbeat & AST State Monitoring (Anti-Hang: missing heartbeat > 120s -> container restart alert)
# C. L3 Supreme Council Escalation (Post-mortem in reflective layer + Correction Plan)

logger = structlog.get_logger("TacticalWatchdog")

API_URL = os.getenv("RAE_API_URL", "http://localhost:8000")
HEADERS = {
    "X-API-Key": os.getenv("RAE_API_KEY", "dev-key"),
    "X-Tenant-Id": os.getenv("RAE_TENANT_ID", "00000000-0000-0000-0000-000000000000"),
}
PROJECT_ID = os.getenv("RAE_HIVE_PROJECT", "RAE-Hive")

# Escalation Thresholds per HIVE-CIRCUIT-BREAKER.md
SWAP_THRESHOLD = 2          # L1: Model Swap
MAX_RETRIES_THRESHOLD = 3   # L3 Circuit Break: 3 rejections
SIMILARITY_THRESHOLD = 0.90 # L3 Circuit Break: Echo loop semantic similarity > 0.90
HEARTBEAT_TIMEOUT_S = 120   # Anti-Hang: 120 seconds max without AST heartbeat

_agent_heartbeats: Dict[str, float] = {}


def calculate_semantic_similarity(text_a: str, text_b: str) -> float:
    """Calculates normalized semantic/token similarity in [0.0, 1.0]."""
    if not text_a or not text_b:
        return 0.0
    a_norm = " ".join(text_a.lower().split())
    b_norm = " ".join(text_b.lower().split())
    if a_norm == b_norm:
        return 1.0
    seq_ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
    tokens_a = set(a_norm.split())
    tokens_b = set(b_norm.split())
    jaccard = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
    return round(max(seq_ratio, jaccard), 4)


def record_agent_heartbeat(agent_id: str, ast_node: str = "Module") -> Dict[str, object]:
    """Records a lightweight AST state heartbeat from an executing agent."""
    now = time.time()
    _agent_heartbeats[agent_id] = now
    return {"agent_id": agent_id, "ast_node": ast_node, "timestamp": now, "status": "ALIVE"}


def check_stale_heartbeats(timeout_seconds: int = HEARTBEAT_TIMEOUT_S) -> List[str]:
    """Returns list of agents whose heartbeat is older than timeout_seconds."""
    now = time.time()
    stale = [
        agent_id
        for agent_id, last_ts in _agent_heartbeats.items()
        if (now - last_ts) > timeout_seconds
    ]
    return stale


async def update_task_metadata(client: httpx.AsyncClient, task_id: str, metadata_updates: dict):
    """Updates task metadata by emitting a new event."""
    payload = {
        "content": f"Watchdog update for {task_id}",
        "layer": "semantic",
        "project": PROJECT_ID,
        "tags": ["hive_task_update"],
        "metadata": {
            "related_task_id": task_id,
            **metadata_updates,
        },
    }
    await client.post(f"{API_URL}/v2/memories/", json=payload, headers=HEADERS)


async def store_reflection(client: httpx.AsyncClient, tier: str, content: str, task_id: str):
    """Stores a hierarchical reflection (L1, L2, or L3 tier)."""
    payload = {
        "content": content,
        "layer": "reflective",
        "project": PROJECT_ID,
        "importance": 0.5 if tier == "L1" else 0.8 if tier == "L2" else 1.0,
        "tags": ["reflection", tier, f"task_{task_id}"],
        "metadata": {
            "task_id": task_id,
            "reflection_tier": tier,
            "audit_standard": "ISO-42001" if tier == "L3" else "Technical",
        },
    }
    await client.post(f"{API_URL}/v2/memories/", json=payload, headers=HEADERS)


async def check_semantic_loops():
    """State-Based Semantic Monitoring (Anti-Echo & Anti-Hang)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Check stale AST heartbeats (Anti-Hang)
        for stale_agent in check_stale_heartbeats():
            logger.warning("silent_hang_detected", agent_id=stale_agent)
            await store_reflection(
                client,
                "L2",
                f"SILENT HANG DETECTED: Agent {stale_agent} missed AST heartbeat > {HEARTBEAT_TIMEOUT_S}s.",
                stale_agent,
            )

        # 2. Fetch tasks currently in progress or review
        try:
            resp = await client.get(
                f"{API_URL}/v2/memories/?project={PROJECT_ID}&layer=semantic&limit=50",
                headers=HEADERS,
            )
            if resp.status_code != 200:
                return
            tasks = resp.json().get("results", [])
        except Exception:
            return

        for task in tasks:
            task_id = task.get("id")
            if not task_id:
                continue

            # Check recent rejections for this specific task in episodic memory
            rej_resp = await client.post(
                f"{API_URL}/v2/memories/query",
                json={
                    "query": f"Audit failed for {task_id}",
                    "project": PROJECT_ID,
                    "layers": ["episodic"],
                    "k": 5,
                },
                headers=HEADERS,
            )

            rejections = rej_resp.json().get("results", []) if rej_resp.status_code == 200 else []
            if len(rejections) < 2:
                continue

            # Calculate pairwise semantic similarity between last two rejection reasons
            latest_reason = rejections[0].get("content", "")
            prev_reason = rejections[1].get("content", "")
            similarity = calculate_semantic_similarity(latest_reason, prev_reason)

            if len(rejections) >= MAX_RETRIES_THRESHOLD or similarity > SIMILARITY_THRESHOLD:
                logger.critical(
                    "echo_loop_circuit_break_triggered",
                    task_id=task_id,
                    rejections_count=len(rejections),
                    semantic_similarity=similarity,
                )
                await update_task_metadata(
                    client,
                    task_id,
                    {
                        "status": "BLOCKED_LOOP",
                        "escalation_status": "BLOCKED_L3",
                        "requires_expert": True,
                        "escalation_level": "L3",
                        "semantic_similarity": similarity,
                        "reason": (
                            f"Echo Loop detected (retries={len(rejections)}, "
                            f"similarity={similarity:.2f} > {SIMILARITY_THRESHOLD})."
                        ),
                    },
                )
                await store_reflection(
                    client,
                    "L3",
                    (
                        f"Task {task_id} failed. Echo Loop detected "
                        f"(retries={len(rejections)}, similarity={similarity:.2f}). "
                        "Escalating to Supreme Council (L3) for Strategic Pivot."
                    ),
                    task_id,
                )


async def watchdog_loop(interval_seconds: int = 60):
    logger.info("Tactical Semantic Watchdog v2.3 (HIVE-CIRCUIT-BREAKER v1.0) active.")
    while True:
        try:
            await check_semantic_loops()
        except Exception as e:
            logger.warning("watchdog_iteration_error", error=str(e))
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(watchdog_loop())
