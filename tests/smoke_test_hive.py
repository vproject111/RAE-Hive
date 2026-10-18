"""
Smoke Test for RAE Hive (Integration).
Verifies the end-to-end flow: Objective -> Orchestrator -> Builder -> Auditor.
"""

import asyncio
import os
import sys
import structlog
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from agent_hive.base_agent.connector import HiveMindConnector
    from agent_hive.planner import add_objective
except ImportError:
    from base_agent.connector import HiveMindConnector
    from planner import add_objective

logger = structlog.get_logger(__name__)

async def run_smoke_test():
    print("🐝 Starting RAE Hive Smoke Test...")
    connector = HiveMindConnector(agent_role="auditor")
    
    # 1. Clean up old test data if any
    # (Optional: depends on if we want a clean state)
    
    # 2. Inject a Smoke Test Objective
    test_goal = "Smoke Test: Create a file named 'smoke_v1.txt' with content 'OK' in work_dir."
    print(f"Injecting objective: {test_goal}")
    await add_objective(test_goal, priority=10)
    
    # 3. Wait and Poll for 'done' status
    # We poll the semantic layer for a task linked to this goal that becomes 'done'
    max_retries = 30
    print("Waiting for agents to process (this uses real LLMs on Node 1)...")
    
    for i in range(max_retries):
        memories = await connector.list_memories(layer="semantic", limit=20)
        
        # Look for the task status
        done_tasks = [m for m in memories if m.get("metadata", {}).get("status") == "done" 
                      and "Smoke Test" in m.get("content", "")]
        
        failed_tasks = [m for m in memories if m.get("metadata", {}).get("status") == "failed"
                        and "Smoke Test" in m.get("content", "")]

        if done_tasks:
            print("✅ SMOKE TEST PASSED: Task marked as DONE by Auditor.")
            return True
        
        if failed_tasks:
            print(f"❌ SMOKE TEST FAILED: Auditor rejected the task. Result: {failed_tasks[0].get('metadata', {}).get('result')}")
            return False
            
        if i % 5 == 0:
            print(f"   ... still waiting ({i*5}s) ...")
            
        await asyncio.sleep(5)
        
    print("⏱️ SMOKE TEST TIMEOUT: Agents took too long.")
    return False

if __name__ == "__main__":
    success = asyncio.run(run_smoke_test())
    sys.exit(0 if success else 1)
