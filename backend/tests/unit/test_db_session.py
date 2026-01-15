"""Unit tests for database session management.

This module contains tests for the database session management functionality, including:
- Async session generator yielding AsyncSession instances
- Context manager behavior for proper cleanup
- Session independence across multiple calls
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db


@pytest.mark.asyncio
async def test_get_db_yields_session():
    """Test that get_db yields an AsyncSession."""
    # GIVEN: The get_db async generator is available
    # WHEN: Iterating over get_db to get a session
    # THEN: An AsyncSession instance is yielded

    async for session in get_db():
        assert isinstance(session, AsyncSession)
        assert session is not None
        break


@pytest.mark.asyncio
async def test_get_db_session_context_manager():
    """Test that get_db works as an async context manager."""
    # GIVEN: The get_db async generator is available
    # WHEN: Using get_db in an async context
    # THEN: Exactly one session is yielded per iteration

    session_count = 0
    async for session in get_db():
        session_count += 1
        assert isinstance(session, AsyncSession)
        break

    assert session_count == 1


@pytest.mark.asyncio
async def test_multiple_get_db_calls_independent():
    """Test that multiple get_db calls yield independent sessions."""
    # GIVEN: The get_db async generator is available
    # WHEN: Calling get_db multiple times
    # THEN: Each call yields a different AsyncSession instance

    sessions = []

    async for session1 in get_db():
        sessions.append(session1)
        break

    async for session2 in get_db():
        sessions.append(session2)
        break

    # Sessions should be different objects
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
