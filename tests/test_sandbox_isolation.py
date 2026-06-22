import os
import shutil
import pytest
from src.sandbox_manager import GitWorktreeManager, DockerSandboxManager

@pytest.fixture
def temp_repo(tmp_path) -> GitWorktreeManager:
    # Setup temporary directory simulating a git repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    # Initialize basic dummy directories
    os.makedirs(repo_dir / "work_dir", exist_ok=True)
    
    # We will use this path to test the worktree manager
    return GitWorktreeManager(repo_root=str(repo_dir))

def test_git_worktree_manager_fallback(temp_repo):
    """Verifies that GitWorktreeManager gracefully falls back to directories if git fails."""
    worktree_path, branch_name = temp_repo.create_worktree()
    
    assert os.path.exists(worktree_path)
    assert "wt_" in worktree_path
    assert "agent/wt-branch-" in branch_name
    
    # Cleanup
    temp_repo.prune_worktree(worktree_path, branch_name)
    assert not os.path.exists(worktree_path)

def test_docker_sandbox_manager_local_fallback():
    """Verifies that DockerSandboxManager executes commands successfully (using local fallback if docker is offline)."""
    sandbox = DockerSandboxManager()
    
    # Create temp execution space
    temp_dir = "./tmp_sandbox_test"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Run a simple echo command
    result = sandbox.run_in_sandbox("echo 'Antigravity'", temp_dir)
    
    assert "exit_code" in result
    assert result["exit_code"] == 0
    assert "Antigravity" in result["stdout"]
    assert result["sandbox_mode"] in ["docker", "local_fallback"]
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
