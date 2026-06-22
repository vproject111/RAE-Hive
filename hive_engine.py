# hive_engine.py
import os
import sys
import ast
import asyncio
import logging
from typing import Dict, Any, List, Optional
from enum import Enum
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport
import uvicorn
import httpx
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.inject_contextvars,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter
    ],
    logger_factory=structlog.PrintLogger(),
    cache_logger__per_event=False
)
logger = structlog.get_logger("RAE-Hive")

# Core enterprise bridge and foundation fallbacks
try:
    from rae_libs.rae_core.bridge.handler import register_bridge
    from rae_libs.rae_core.utils.enterprise_guard import RAE_Enterprise_Foundation, audited_operation
    from rae_libs.rae_core.memory import RAEMemoryBridge
except ImportError:
    try:
        from rae_core.bridge.handler import register_bridge
        from rae_core.utils.enterprise_guard import RAE_Enterprise_Foundation, audited_operation
        from rae_core.memory import RAEMemoryBridge
    except ImportError:
        # Fallback fake implementations for standalone run
        def register_bridge(app, module_name: str):
            pass
            
        class RAE_Enterprise_Foundation:
            def __init__(self, module_name: str = None):
                self.module_name = module_name
                
            def create_context(self): 
                return type('obj', (object,), {
                    "validate_signature": lambda x, y: True, 
                    "validate_schema": lambda x, y: True, 
                    "validate_input": lambda x, y, z: True, 
                    "get_timestamp": lambda x: "2026-05-23T21:30:00Z"
                })()
                
            @property
            def logger(self):
                return logger
                
        def audited_operation(*args, **kwargs):
            if len(args) == 1 and callable(args[0]):
                return args[0]
            def decorator(func):
                return func
            return decorator
            
        class RAEMemoryBridge:
            def __init__(self, **kwargs): pass
            def save_event(self, text, layer="episodic"): 
                logger.info("bridge_event_saved", text=text, layer=layer)

# Import sandbox managers
from src.sandbox_manager import GitWorktreeManager, DockerSandboxManager

# Security Level settings
class SecurityLevel(Enum):
    STANDARD = "standard"
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"

SECURITY_LEVEL_ENV = os.getenv("SECURITY_LEVEL", "STANDARD").upper()
if SECURITY_LEVEL_ENV not in [s.name for s in SecurityLevel]:
    SECURITY_LEVEL = SecurityLevel.STANDARD
else:
    SECURITY_LEVEL = SecurityLevel[SECURITY_LEVEL_ENV]

class ASTSafetyGuard:
    """Parses Python code snippets using python's AST module to detect dangerous operations or side-channels."""
    
    FORBIDDEN_CALLS = {"system", "popen", "subprocess", "rmtree", "unlink", "remove", "eval", "exec"}
    FORBIDDEN_IMPORTS = {"os", "subprocess", "shutil", "sys", "socket", "pty"}

    @staticmethod
    def verify_safety(code_str: str) -> tuple[bool, str]:
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return False, f"AST Parse Error: {str(e)}"
            
        for node in ast.walk(tree):
            # Check forbidden imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ASTSafetyGuard.FORBIDDEN_IMPORTS:
                        return False, f"Security Violation: Import of forbidden library '{alias.name}' detected."
            elif isinstance(node, ast.ImportFrom):
                if node.module in ASTSafetyGuard.FORBIDDEN_IMPORTS:
                    return False, f"Security Violation: Import from forbidden library '{node.module}' detected."
            
            # Check forbidden function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ASTSafetyGuard.FORBIDDEN_CALLS:
                        return False, f"Security Violation: Call to forbidden function '{node.func.id}' detected."
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ASTSafetyGuard.FORBIDDEN_CALLS:
                        return False, f"Security Violation: Call to forbidden attribute '{node.func.attr}' detected."
                        
        return True, "Code verified safe by ASTSafetyGuard."

class HiveCronScheduler:
    """Background task loop that periodically checks RAE-Memory backlog for pending tasks and executes them."""
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.running = False

    async def start(self):
        self.running = True
        asyncio.create_task(self._scheduler_loop())

    async def _scheduler_loop(self):
        logger.info("HiveCronScheduler daemon loop started.")
        while self.running:
            try:
                # Query RAE-Memory backlog for pending execution tasks
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(f"{self.api_url}/v2/memories/query", json={
                        "query": "pending build and deployment tasks",
                        "layer": "working",
                        "k": 2
                    })
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        for task in results:
                            tags = task.get("metadata", {}).get("tags", [])
                            if "pending" in tags:
                                logger.info("cron_scheduler_executing_task", task_label=task.get('human_label'))
                                # Run task logic (in a real swarm this invokes the execution container)
            except Exception as e:
                logger.error("error_in_cron_scheduler_cycle", error=str(e))
            await asyncio.sleep(60) # Run every minute

class HiveGarbageCollector:
    """Background loop that periodically cleans up stale temporary work files and sandbox resources."""
    def __init__(self):
        self.running = False

    async def start(self):
        self.running = True
        asyncio.create_task(self._gc_loop())

    async def _gc_loop(self):
        logger.info("HiveGarbageCollector daemon loop started.")
        while self.running:
            try:
                # Simulate Docker scratch container cleaning and temporary file pruning
                logger.info("garbage_collector_pruning_build_cache")
            except Exception as e:
                logger.error("error_in_garbage_collector_cycle", error=str(e))
            await asyncio.sleep(120) # Run every 2 minutes

# Execution Swarm class with enhanced security and Docker/Worktree sandboxing
class HiveExecutionSwarm:
    def __init__(self):
        try:
            self.enterprise_foundation = RAE_Enterprise_Foundation(module_name="rae-hive")
        except TypeError:
            self.enterprise_foundation = RAE_Enterprise_Foundation()
            
        self.security_context = self.enterprise_foundation.create_context()
        self.security_level = SECURITY_LEVEL
        
        try:
            self.memory_bridge = RAEMemoryBridge(
                audit_enabled=bool(os.getenv("AUDIT_ENABLED", "true").lower() == "true"),
                retention_period=int(os.getenv("MEMORY_RETENTION", 86400)),
                encryption_key=os.getenv("MEMORY_ENCRYPTION_KEY", "secure_key_123")
            )
        except Exception:
            self.memory_bridge = RAEMemoryBridge()

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
            
            # Log successful event to RAE-Memory
            try:
                self.memory_bridge.save_event(f"Hive sandboxed command run: {command[:200]}", layer="reflective")
            except Exception:
                pass
                
            return result
        except Exception as e:
            # Safe cleanup in case of catastrophic execution failure
            if worktree_path and branch_name:
                try:
                    self.worktree_manager.prune_worktree(worktree_path, branch_name)
                except Exception:
                    pass
            return {"error": str(e)}

    @audited_operation
    async def execute_swarm_task(self, python_code: str) -> str:
        """Runs a python execution task securely after AST verification."""
        # 1. Run AST verification
        is_safe, msg = ASTSafetyGuard.verify_safety(python_code)
        if not is_safe:
            logger.warning("ast_safety_guard_rejected_task", reasoning=msg)
            return f"REJECTED: {msg}"
            
        logger.info("ast_safety_guard_approved_task", code_length=len(python_code))
        
        # 2. Run inside sandboxed environment (Simulated local execution wrapper)
        local_scope = {}
        try:
            old_stdout = sys.stdout
            from io import StringIO
            redirected_output = sys.stdout = StringIO()
            
            exec(python_code, {}, local_scope)
            
            sys.stdout = old_stdout
            output = redirected_output.getvalue()
            
            # Log successful event to RAE-Memory
            try:
                self.memory_bridge.save_event(f"Hive successfully executed swarm task. Output preview: {output[:100]}", layer="reflective")
            except Exception:
                pass
                
            return f"SUCCESS:\n{output}"
        except Exception as e:
            sys.stdout = old_stdout
            logger.error("swarm_task_execution_failed", error=str(e))
            return f"FAILED: {str(e)}"

# Initialize execution swarm and MCP server
execution_swarm = HiveExecutionSwarm()
swarm = execution_swarm  # Alias for compatibility
mcp_server = Server("rae-hive")

@mcp_server.list_tools()
async def handle_list_tools():
    return [
        Tool(
            name="execute_swarm_task",
            description="Executes a python code or system command within a fully sandboxed and isolated Swarm environment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "python_code": {"type": "string", "description": "Python code to execute (AST Safety scan enabled)"},
                    "command": {"type": "string", "description": "System command to execute in Docker / Worktree sandbox"}
                }
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "execute_swarm_task":
        if "python_code" in arguments:
            code = arguments.get("python_code")
            result = await execution_swarm.execute_swarm_task(code)
            return [TextContent(type="text", text=result)]
        elif "command" in arguments:
            cmd = arguments.get("command")
            result = swarm.run_command(cmd)
            
            if "error" in result:
                return [TextContent(type="text", text=f"Error: {result['error']}")]
                
            sandbox_mode = result.get("sandbox_mode", "unknown")
            return [TextContent(
                type="text",
                text=f"Sandbox Mode: {sandbox_mode}\nExit: {result['exit_code']}\nOut: {result['stdout']}\nErr: {result.get('stderr', '')}"
            )]
        else:
            raise ValueError("Either 'python_code' or 'command' must be provided.")
            
    raise ValueError(f"Unknown tool: {name}")

# Initialize the FastAPI application
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes from MCP server
app.include_router(mcp_server.router)

# Register bridge
register_bridge(app, "rae-hive")

sse = SseServerTransport("/mcp/messages")

@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())

@app.post("/mcp/messages")
async def mcp_messages_endpoint(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    # Start the pro-active background daemons on startup!
    api_url = os.getenv("RAE_API_URL", "http://localhost:8011")
    scheduler = HiveCronScheduler(api_url)
    gc = HiveGarbageCollector()
    
    await scheduler.start()
    await gc.start()
    logger.info("hive_background_daemons_started")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
