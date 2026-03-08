"""Shared test fixtures for Tracely backend tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from backend.config import Settings
from backend.entity_map import EntityMap
from backend.normalizer import Normalizer
from backend.storage import Storage
from backend.tree_builder import TreeBuilder

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from the fixtures directory."""
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_path = str(tmp_path / "test_tracely.db")
    return Settings(
        db_path=db_path,
        ha_url="ws://localhost:8123/api/websocket",
        ha_token="test_token",
        log_level="debug",
        purge_keep_days=7,
        infer_window_ms=3000,
        dedup_window_ms=500,
        aggregate_threshold_per_sec=5,
    )


@pytest_asyncio.fixture
async def db(settings: Settings) -> Storage:
    store = Storage(settings)
    await store.init()
    yield store
    await store.close()


@pytest.fixture
def entity_map() -> EntityMap:
    em = EntityMap()
    em.load_states([
        {
            "entity_id": "light.kitchen",
            "attributes": {"friendly_name": "Kitchen Light"},
        },
        {
            "entity_id": "automation.evening_lights",
            "attributes": {"friendly_name": "Evening Lights"},
        },
        {
            "entity_id": "sensor.temperature",
            "attributes": {"friendly_name": "Temperature Sensor"},
        },
        {
            "entity_id": "switch.fan",
            "attributes": {"friendly_name": "Living Room Fan"},
        },
    ])
    return em


@pytest.fixture
def normalizer_instance(entity_map: EntityMap) -> Normalizer:
    return Normalizer(entity_map)


@pytest_asyncio.fixture
async def tree_builder(db: Storage, settings: Settings) -> TreeBuilder:
    return TreeBuilder(db, settings)


@pytest.fixture
def state_changed_event() -> dict:
    return load_fixture("state_changed.json")


@pytest.fixture
def call_service_event() -> dict:
    return load_fixture("call_service.json")


@pytest.fixture
def automation_triggered_event() -> dict:
    return load_fixture("automation_triggered.json")
