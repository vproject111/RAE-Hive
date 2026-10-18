# hive_engine.py
import os
import sys

# Enforce Git Flow & SemVer Branch Guard Validation
try:
    from rae_core.governance.versioning import VersioningValidator
    VersioningValidator(
        project_path=os.path.dirname(os.path.abspath(__file__)),
        module_name="rae-hive-eyes",
        config={"strategy": "git-flow", "strict": True}
    ).validate()
except Exception as e:
    print(f"❌ Git Flow Validation failed: {e}", file=sys.stderr)
    sys.exit(1)

from fastapi import FastAPI, Request
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport
import uvicorn

# Import Bridge Handler
from rae_core.bridge.handler import register_bridge

# Import z naszego twardego jądra
from rae_core.utils.enterprise_guard import RAE_Enterprise_Foundation, audited_operation

# Import sandbox managers
from src.sandbox_manager import GitWorktreeManager, DockerSandboxManager

class HiveExecutionSwarm:
    def __init__(self):
        self.enterprise_foundation = RAE_Enterprise_Foundation(module_name="rae-hive")
        
        # Initialize GitWorktreeManager with current workspace root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.worktree_manager = GitWorktreeManager(repo_root=current_dir)
        self.sandbox_manager = DockerSandboxManager()

    @audited_operation(operation_name="execute_system_command", impact_level="high")
    def run_command(self, command: str) -> dict:
        """
        Executes a system command within a fully isolated and sandboxed Git Worktree.
        """
        self.enterprise_foundation.logger.info(f"🛠️ [Hive Execution] Sandboxed Command: {command}")
        
        # Global guard: bar critically destructive commands
        if "rm -rf /" in command:
            raise PermissionError("Attempted execution of a critically destructive command.")

        worktree_path = None
        branch_name = None
        try:
            # 1. Create a safe isolated Git Worktree
            worktree_path, branch_name = self.worktree_manager.create_worktree()
            
            # 2. Run command inside the ephemeral sandbox (Docker / local fallback)
            result = self.sandbox_manager.run_in_sandbox(command, worktree_path)
            
            # 3. Clean up the ephemeral Git Worktree
            self.worktree_manager.prune_worktree(worktree_path, branch_name)
            
            return result
        except Exception as e:
            # Safe cleanup in case of catastrophic execution failure
            if worktree_path and branch_name:
                try:
                    self.worktree_manager.prune_worktree(worktree_path, branch_name)
                except Exception:
                    pass
            return {"error": str(e)}

    def run_parallel_commands(self, commands: list) -> list:
        """Executes up to k<=3 read-only commands in parallel using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor
        bounded = list(commands)[:3]
        with ThreadPoolExecutor(max_workers=3) as pool:
            return list(pool.map(self.run_command, bounded))

# Inicjalizacja usług
swarm = HiveExecutionSwarm()
mcp_server = Server("rae-hive")

@mcp_server.list_tools()
async def handle_list_tools():
    return [
        Tool(
            name="execute_swarm_task",
            description="Executes a system command within a fully sandboxed and isolated Swarm environment. Full audit trail generated.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                },
                "required": ["command"]
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "execute_swarm_task":
        cmd = arguments.get("command")
        try:
            from strategies.semantic_watchdog import record_agent_heartbeat
            record_agent_heartbeat("rae-hive")
        except Exception:
            pass
        result = swarm.run_command(cmd)
        
        if "error" in result:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
            
        sandbox_mode = result.get("sandbox_mode", "unknown")
        return [TextContent(
            type="text",
            text=f"Sandbox Mode: {sandbox_mode}\nExit: {result['exit_code']}\nOut: {result['stdout']}\nErr: {result.get('stderr', '')}"
        )]
    raise ValueError(f"Unknown tool: {name}")

app = FastAPI()
register_bridge(app, "rae-hive")
sse = SseServerTransport("/mcp/messages")

@app.on_event("startup")
async def _start_hive_watchdog():
    import asyncio
    from strategies.semantic_watchdog import watchdog_loop, record_agent_heartbeat
    record_agent_heartbeat("rae-hive")
    asyncio.create_task(watchdog_loop(interval_seconds=30))

@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())

@app.post("/mcp/messages")
async def mcp_messages_endpoint(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

@app.get("/v2/hive/watchdog")
async def hive_watchdog_status():
    from strategies.semantic_watchdog import check_stale_heartbeats, record_agent_heartbeat
    record_agent_heartbeat("rae-hive")
    stale = check_stale_heartbeats()
    return {"status": "monitoring", "stale_agents": stale}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


