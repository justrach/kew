# kew/tests/conftest.py
import pytest
import asyncio
from kew import TaskQueueManager

@pytest.fixture
async def manager():
    """Fixture that provides a TaskQueueManager instance"""
    manager = TaskQueueManager()
    yield manager
    await manager.shutdown()
