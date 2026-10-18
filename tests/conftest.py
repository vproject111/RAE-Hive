"""
Configuration and fixtures for RAE Hive tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import os
import sys
from pathlib import Path

# Ensure rae-hive package root is in sys.path
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

try:
    from agent_hive.base_agent.connector import HiveMindConnector
except ImportError:
    from base_agent.connector import HiveMindConnector

@pytest.fixture
def mock_connector():
    """Fixture to provide a connector with mocked HTTP calls."""
    connector = HiveMindConnector(agent_role="test_agent")
    connector.headers = {"X-API-Key": "test", "X-Tenant-Id": "test"}
    return connector

@pytest.fixture
def sample_task_memory():
    """Returns a sample task memory as it would come from the API."""
    return {
        "id": "task-uuid-123",
        "content": "Test Task Content",
        "layer": "semantic",
        "tags": ["hive_task", "test_agent", "pending"],
        "metadata": {
            "task_id": "T-001",
            "assignee": "test_agent",
            "status": "pending"
        }
    }
