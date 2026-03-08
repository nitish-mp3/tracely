"""Tests for Storage — insert, read, CTE tree query, FTS search, purge."""

from __future__ import annotations

import json
import time

import pytest

from backend.models import EventRecord
from backend.storage import Storage


def _make_event(
    eid: str = "ev1",
    parent: str | None = None,
    entity: str = "light.kitchen",
    etype: str = "state_changed",
    ts: int | None = None,
    name: str = "Kitchen Light changed to on",
) -> EventRecord:
    return EventRecord(
        id=eid,
        parent_id=parent,
        event_type=etype,
        domain="light",
        service=None,
        entity_id=entity,
        payload=json.dumps({"state": "on"}),
        name=name,
        integration=None,
        area=None,
        timestamp=ts or int(time.time() * 1000),
        user_id=None,
        important=0,
        confidence="propagated" if parent else "inferred",
        generated_root=0,
    )


@pytest.mark.asyncio
async def test_insert_and_read(db: Storage) -> None:
    event = _make_event()
    await db.insert_event(event)

    result = await db.get_event("ev1")
    assert result is not None
    assert result["id"] == "ev1"
    assert result["entity_id"] == "light.kitchen"


@pytest.mark.asyncio
async def test_batch_insert(db: Storage) -> None:
    events = [_make_event(eid=f"batch_{i}") for i in range(10)]
    await db.insert_events_batch(events)

    rows, total = await db.get_events(page=1, limit=50)
    assert total == 10
    assert len(rows) == 10


@pytest.mark.asyncio
async def test_pagination(db: Storage) -> None:
    now = int(time.time() * 1000)
    events = [_make_event(eid=f"page_{i}", ts=now + i) for i in range(25)]
    await db.insert_events_batch(events)

    rows, total = await db.get_events(page=1, limit=10)
    assert total == 25
    assert len(rows) == 10

    rows2, _ = await db.get_events(page=3, limit=10)
    assert len(rows2) == 5


@pytest.mark.asyncio
async def test_filter_by_entity(db: Storage) -> None:
    await db.insert_event(_make_event(eid="e1", entity="light.kitchen"))
    await db.insert_event(_make_event(eid="e2", entity="switch.fan"))
    await db.insert_event(_make_event(eid="e3", entity="light.kitchen"))

    rows, total = await db.get_events(entity="light.kitchen")
    assert total == 2
    assert all(r["entity_id"] == "light.kitchen" for r in rows)


@pytest.mark.asyncio
async def test_tree_cte(db: Storage) -> None:
    now = int(time.time() * 1000)
    await db.insert_event(_make_event(eid="root", ts=now))
    await db.insert_event(_make_event(eid="child1", parent="root", ts=now + 1))
    await db.insert_event(_make_event(eid="child2", parent="root", ts=now + 2))
    await db.insert_event(_make_event(eid="grandchild", parent="child1", ts=now + 3))

    tree = await db.get_tree("root")
    assert len(tree) == 4
    ids = {n["id"] for n in tree}
    assert ids == {"root", "child1", "child2", "grandchild"}


@pytest.mark.asyncio
async def test_find_root(db: Storage) -> None:
    now = int(time.time() * 1000)
    await db.insert_event(_make_event(eid="r", ts=now))
    await db.insert_event(_make_event(eid="c1", parent="r", ts=now + 1))
    await db.insert_event(_make_event(eid="c2", parent="c1", ts=now + 2))

    root = await db.find_root("c2")
    assert root == "r"


@pytest.mark.asyncio
async def test_fts_search(db: Storage) -> None:
    await db.insert_event(
        _make_event(eid="fts1", name="Kitchen Light turned on"),
    )
    await db.insert_event(
        _make_event(eid="fts2", name="Bedroom Fan started", entity="fan.bedroom"),
    )

    results = await db.search_fts("Kitchen")
    assert len(results) == 1
    assert results[0]["id"] == "fts1"


@pytest.mark.asyncio
async def test_bookmark(db: Storage) -> None:
    await db.insert_event(_make_event(eid="bm1"))
    ok = await db.bookmark("bm1", "important event")
    assert ok is True

    event = await db.get_event("bm1")
    assert event is not None
    assert event["important"] == 1


@pytest.mark.asyncio
async def test_purge(db: Storage) -> None:
    old_ts = int((time.time() - 100_000) * 1000)
    new_ts = int(time.time() * 1000)
    await db.insert_event(_make_event(eid="old", ts=old_ts))
    await db.insert_event(_make_event(eid="new", ts=new_ts))

    cutoff = int((time.time() - 50_000) * 1000)
    deleted = await db.purge_old_events(cutoff)
    assert deleted == 1

    remaining, total = await db.get_events()
    assert total == 1
    assert remaining[0]["id"] == "new"


@pytest.mark.asyncio
async def test_stats(db: Storage) -> None:
    assert await db.get_event_count() == 0

    await db.insert_event(_make_event(eid="s1"))
    assert await db.get_event_count() == 1
    assert await db.get_last_event_ts() is not None
    assert await db.get_db_size() > 0
