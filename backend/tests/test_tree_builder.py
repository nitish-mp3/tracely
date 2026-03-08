"""Tests for TreeBuilder — parent/child linking and heuristic scenarios."""

from __future__ import annotations

import json
import time

import pytest

from backend.models import EventRecord
from backend.storage import Storage
from backend.tree_builder import TreeBuilder


def _event(
    eid: str,
    parent: str | None = None,
    entity: str = "light.kitchen",
    etype: str = "state_changed",
    ts: int | None = None,
    user_id: str | None = None,
) -> EventRecord:
    return EventRecord(
        id=eid,
        parent_id=parent,
        event_type=etype,
        domain="light",
        service=None,
        entity_id=entity,
        payload=json.dumps({"state": "on"}),
        name="test event",
        integration=None,
        area=None,
        timestamp=ts or int(time.time() * 1000),
        user_id=user_id,
        important=0,
        confidence="propagated" if parent else "inferred",
        generated_root=0,
    )


@pytest.mark.asyncio
async def test_link_with_parent_id(
    db: Storage, tree_builder: TreeBuilder,
) -> None:
    """Events with explicit parent_id should not be re-linked."""
    parent = _event("parent")
    child = _event("child", parent="parent")
    await db.insert_event(parent)
    await db.insert_event(child)

    await tree_builder.link(child)
    result = await db.get_event("child")
    assert result is not None
    assert result["parent_id"] == "parent"
    assert result["confidence"] == "propagated"


@pytest.mark.asyncio
async def test_infer_by_call_service(
    db: Storage, tree_builder: TreeBuilder,
) -> None:
    """Rule 2: should infer parent from recent call_service on same entity."""
    now = int(time.time() * 1000)
    svc = _event("svc1", entity="light.kitchen", etype="call_service", ts=now - 1000)
    state = _event("state1", entity="light.kitchen", ts=now)

    await db.insert_event(svc)
    await db.insert_event(state)
    await tree_builder.link(state)

    result = await db.get_event("state1")
    assert result is not None
    assert result["parent_id"] == "svc1"
    assert result["confidence"] == "inferred"


@pytest.mark.asyncio
async def test_infer_by_user_entity(
    db: Storage, tree_builder: TreeBuilder,
) -> None:
    """Rule 3: should infer parent from same user + same entity."""
    now = int(time.time() * 1000)
    ev1 = _event("u1", entity="switch.fan", user_id="alice", ts=now - 500)
    ev2 = _event("u2", entity="switch.fan", user_id="alice", ts=now)

    await db.insert_event(ev1)
    await db.insert_event(ev2)
    await tree_builder.link(ev2)

    result = await db.get_event("u2")
    assert result is not None
    assert result["parent_id"] == "u1"


@pytest.mark.asyncio
async def test_infer_by_same_entity(
    db: Storage, tree_builder: TreeBuilder,
) -> None:
    """Rule 4: should infer parent from same entity within window."""
    now = int(time.time() * 1000)
    ev1 = _event("e1", entity="sensor.temp", ts=now - 2000)
    ev2 = _event("e2", entity="sensor.temp", ts=now)

    await db.insert_event(ev1)
    await db.insert_event(ev2)
    await tree_builder.link(ev2)

    result = await db.get_event("e2")
    assert result is not None
    assert result["parent_id"] == "e1"


@pytest.mark.asyncio
async def test_no_link_outside_window(
    db: Storage, tree_builder: TreeBuilder,
) -> None:
    """Events outside the infer window should not be linked."""
    now = int(time.time() * 1000)
    ev1 = _event("old1", entity="light.kitchen", ts=now - 10_000)
    ev2 = _event("new1", entity="light.kitchen", ts=now)

    await db.insert_event(ev1)
    await db.insert_event(ev2)
    await tree_builder.link(ev2)

    result = await db.get_event("new1")
    assert result is not None
    # Should remain unlinked (no parent within window)
    assert result["parent_id"] is None


@pytest.mark.asyncio
async def test_tree_summary(db: Storage, tree_builder: TreeBuilder) -> None:
    now = int(time.time() * 1000)
    await db.insert_event(_event("r", ts=now))
    await db.insert_event(_event("c1", parent="r", ts=now + 100))
    await db.insert_event(_event("c2", parent="r", ts=now + 200))

    summary = await tree_builder.build_tree_summary("r")
    assert summary["event_count"] == 3
    assert summary["duration_ms"] == 200


def test_generate_event_id() -> None:
    eid = TreeBuilder.generate_event_id('{"test": true}')
    assert isinstance(eid, str)
    assert len(eid) == 32
