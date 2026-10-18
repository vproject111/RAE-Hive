"""
Unit tests for HiveMindConnector.
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx
try:
    from agent_hive.base_agent.connector import HiveMindConnector
except ImportError:
    from base_agent.connector import HiveMindConnector

@pytest.mark.asyncio
async def test_connector_list_memories(mock_connector):
    """Test fetching memories with mocked response."""
    mock_response = {
        "results": [
            {"id": "1", "content": "Memory 1", "tags": ["tag1"]},
            {"id": "2", "content": "Memory 2", "tags": ["tag2"]}
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        
        # 1. Test basic list
        results = await mock_connector.list_memories(layer="semantic")
        assert len(results) == 2
        assert results[0]["content"] == "Memory 1"
        
        # 2. Test with tag filter (client-side)
        filtered = await mock_connector.list_memories(tags=["tag2"])
        assert len(filtered) == 1
        assert filtered[0]["id"] == "2"

@pytest.mark.asyncio
async def test_connector_add_memory(mock_connector):
    """Test adding a memory."""
    mock_response = {"memory_id": "new-uuid", "message": "stored"}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        
        result = await mock_connector.add_memory(content="New info", layer="episodic", tags=["test"])
        assert result["memory_id"] == "new-uuid"
        
        # Verify payload
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["content"] == "New info"
        assert kwargs["json"]["layer"] == "episodic"

@pytest.mark.asyncio
async def test_connector_get_tasks(mock_connector, sample_task_memory):
    """Test high-level get_tasks logic."""
    mock_response = {"results": [sample_task_memory]}
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        
        tasks = await mock_connector.get_tasks(status="pending")
        assert len(tasks) == 1
        assert tasks[0]["metadata"]["task_id"] == "T-001"

from unittest.mock import MagicMock
