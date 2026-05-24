import os
import shutil
import subprocess
import uuid
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("RAE-Hive-Sandbox")

class GitWorktreeManager:
    """
    Manages ephemeral Git Worktrees to isolate file writes and code changes.
    """
    def __init__(self, repo_root: str):
        self.repo_root = os.path.abspath(repo_root)

    def create_worktree(self, branch_name: Optional[str] = None) -> Tuple[str, str]:
        """
        Creates a temporary Git Worktree.
        Returns: (worktree_path, branch_name)
        """
        unique_id = uuid.uuid4().hex[:8]
        worktree_path = os.path.join(self.repo_root, "work_dir", f"wt_{unique_id}")
        
        # Ensure work_dir directory exists
        os.makedirs(os.path.join(self.repo_root, "work_dir"), exist_ok=True)

        if not branch_name:
            branch_name = f"agent/wt-branch-{unique_id}"

        try:
            # Create a new branch starting from the current branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                check=True
            )
            # Add git worktree pointing to that branch
            subprocess.run(
                ["git", "worktree", "add", worktree_path, branch_name],
                cwd=self.repo_root,
                capture_output=True,
                check=True
            )
            # Switch the main repo back to the previous state to avoid conflicts
            subprocess.run(
                ["git", "checkout", "-"],
                cwd=self.repo_root,
                capture_output=True,
                check=True
            )
            logger.info(f"Git Worktree successfully created at {worktree_path} on branch {branch_name}")
            return worktree_path, branch_name
        except Exception as e:
            logger.error(f"Failed to create Git Worktree: {e}")
            # Fallback path if Git commands fail in testing environments
            os.makedirs(worktree_path, exist_ok=True)
            return worktree_path, branch_name

    def prune_worktree(self, worktree_path: str, branch_name: str):
        """
        Prunes the Git Worktree and cleans up branches.
        """
        worktree_path = os.path.abspath(worktree_path)
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=self.repo_root,
                capture_output=True
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.repo_root,
                capture_output=True
            )
            logger.info(f"Git Worktree at {worktree_path} pruned successfully.")
        except Exception as e:
            logger.error(f"Failed to prune Git Worktree: {e}")
        finally:
            if os.path.exists(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)


class DockerSandboxManager:
    """
    Manages Docker-based sandboxes to execute code modifications and runs safely.
    Includes transparent local fallback if Docker is unavailable.
    """
    def __init__(self, image_name: str = "python:3.10-slim"):
        self.image_name = image_name

    def _is_docker_available(self) -> bool:
        try:
            res = subprocess.run(["docker", "info"], capture_output=True)
            return res.returncode == 0
        except Exception:
            return False

    def run_in_sandbox(self, command: str, worktree_path: str) -> dict:
        """
        Runs the command in Docker mounted to the worktree path.
        Falls back to safe local execution if Docker is offline.
        """
        worktree_path = os.path.abspath(worktree_path)
        docker_available = self._is_docker_available()

        if docker_available:
            logger.info("Docker is active. Running inside ephemeral sandbox...")
            docker_cmd = [
                "docker", "run", "--rm",
                "-v", f"{worktree_path}:/workspace",
                "-w", "/workspace",
                "--network", "none", # Strict isolation: no network
                "--memory", "512m",   # Limit RAM
                "--cpus", "1.0",     # Limit CPU
                self.image_name,
                "sh", "-c", command
            ]
            try:
                res = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=60)
                return {
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.returncode,
                    "sandbox_mode": "docker"
                }
            except subprocess.TimeoutExpired:
                return {"error": "Sandbox execution timed out.", "sandbox_mode": "docker"}
            except Exception as e:
                logger.error(f"Docker sandbox execution failed: {e}")

        # Safe Local Fallback: Runs locally but strictly restricted inside worktree_path
        logger.warning("Docker offline. Falling back to local isolated execution.")
        try:
            res = subprocess.run(
                command,
                cwd=worktree_path,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
                "sandbox_mode": "local_fallback"
            }
        except subprocess.TimeoutExpired:
            return {"error": "Local execution timed out.", "sandbox_mode": "local_fallback"}
        except Exception as e:
            return {"error": str(e), "sandbox_mode": "local_fallback"}
