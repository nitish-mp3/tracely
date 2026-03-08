"""Tests for Normalizer — label generation for all HA event types."""

from __future__ import annotations

from backend.normalizer import Normalizer


def test_label_state_changed_on(
    normalizer_instance: Normalizer,
    state_changed_event: dict,
) -> None:
    data = state_changed_event["data"]
    label = normalizer_instance.label("state_changed", data, "light.kitchen")
    assert "Kitchen Light" in label
    assert "on" in label


def test_label_state_changed_numeric(normalizer_instance: Normalizer) -> None:
    data = {
        "entity_id": "sensor.temperature",
        "old_state": {"state": "21.5"},
        "new_state": {"state": "22.0"},
    }
    label = normalizer_instance.label("state_changed", data, "sensor.temperature")
    assert "Temperature Sensor" in label
    assert "22.0" in label


def test_label_call_service(
    normalizer_instance: Normalizer,
    call_service_event: dict,
) -> None:
    data = call_service_event["data"]
    label = normalizer_instance.label("call_service", data, "light.kitchen")
    assert "Kitchen Light" in label
    assert "turn on" in label


def test_label_automation_triggered(
    normalizer_instance: Normalizer,
    automation_triggered_event: dict,
) -> None:
    data = automation_triggered_event["data"]
    label = normalizer_instance.label(
        "automation_triggered", data, "automation.evening_lights",
    )
    assert "Evening Lights" in label
    assert "triggered" in label


def test_label_script_started(normalizer_instance: Normalizer) -> None:
    data = {"entity_id": "script.morning_routine"}
    label = normalizer_instance.label("script_started", data, "script.morning_routine")
    assert "started" in label


def test_label_script_finished(normalizer_instance: Normalizer) -> None:
    data = {"entity_id": "script.morning_routine"}
    label = normalizer_instance.label("script_finished", data, "script.morning_routine")
    assert "finished" in label


def test_label_ha_start(normalizer_instance: Normalizer) -> None:
    label = normalizer_instance.label("homeassistant_start", {})
    assert label == "Home Assistant started"


def test_label_ha_stop(normalizer_instance: Normalizer) -> None:
    label = normalizer_instance.label("homeassistant_stop", {})
    assert label == "Home Assistant stopped"


def test_label_logbook(normalizer_instance: Normalizer) -> None:
    data = {"name": "Kitchen Light", "message": "turned on"}
    label = normalizer_instance.label("logbook_entry", data)
    assert "Kitchen Light" in label
    assert "turned on" in label


def test_label_unknown_type(normalizer_instance: Normalizer) -> None:
    label = normalizer_instance.label("some_custom_event", {})
    assert "some_custom_event" in label


def test_extract_entity_state_changed(normalizer_instance: Normalizer) -> None:
    data = {"entity_id": "light.kitchen"}
    eid = normalizer_instance.extract_entity_id("state_changed", data)
    assert eid == "light.kitchen"


def test_extract_entity_call_service_list(
    normalizer_instance: Normalizer,
) -> None:
    data = {"service_data": {"entity_id": ["light.kitchen", "light.bedroom"]}}
    eid = normalizer_instance.extract_entity_id("call_service", data)
    assert eid == "light.kitchen"


def test_extract_domain_service(normalizer_instance: Normalizer) -> None:
    data = {"domain": "light", "service": "turn_on"}
    domain, service = normalizer_instance.extract_domain_service("call_service", data)
    assert domain == "light"
    assert service == "turn_on"
