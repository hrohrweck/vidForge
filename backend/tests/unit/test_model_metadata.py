import pytest

from app.services.model_metadata import (
    get_model_constraint,
    merge_capabilities,
    merge_constraints,
    merge_cost_config,
    normalize_cost_config,
)


def test_normalize_cost_config_maps_compute_points():
    assert normalize_cost_config({"compute_points": 50}) == {
        "cost_per_image": 50,
        "compute_points": 50,
    }


def test_normalize_cost_config_preserves_canonical_keys():
    raw = {
        "cost_per_image": 0.02,
        "cost_per_second": 0.01,
        "currency": "USD",
        "custom_key": "keep-me",
    }
    assert normalize_cost_config(raw) == raw


def test_merge_cost_config_preserves_existing_price():
    existing = {"cost_per_image": 0.01, "currency": "USD"}
    discovered = {"currency": "credits"}
    assert merge_cost_config(existing, discovered) == {
        "cost_per_image": 0.01,
        "currency": "credits",
    }


def test_merge_cost_config_does_not_wipe_on_empty_discovery():
    existing = {"cost_per_image": 0.01}
    assert merge_cost_config(existing, {}) == existing


def test_merge_cost_config_overwrites_when_provider_returns_value():
    existing = {"cost_per_image": 0.01, "currency": "USD"}
    discovered = {"compute_points": 100}
    assert merge_cost_config(existing, discovered) == {
        "cost_per_image": 100,
        "currency": "USD",
        "compute_points": 100,
    }


def test_merge_constraints_prefers_discovered():
    existing = {"max_duration": 10}
    discovered = {"max_duration": 5, "max_prompt_length": 400}
    assert merge_constraints(existing, discovered) == {
        "max_duration": 5,
        "max_prompt_length": 400,
    }


def test_merge_constraints_preserves_unknown_extras():
    existing = {"custom_constraint": "value"}
    discovered = {"max_duration": 5}
    assert merge_constraints(existing, discovered) == {
        "custom_constraint": "value",
        "max_duration": 5,
    }


def test_merge_capabilities_normalizes_booleans():
    existing = {"accepts_text": False, "custom_flag": True}
    discovered = {"accepts_text": 1, "outputs_image": "yes"}
    result = merge_capabilities(existing, discovered)
    assert result["accepts_text"] is True
    assert result["outputs_image"] is True
    assert result["custom_flag"] is True


def test_get_model_constraint_looks_in_constraints():
    assert get_model_constraint({"constraints": {"max_duration": 5}}, "max_duration") == 5


def test_get_model_constraint_looks_at_top_level():
    assert get_model_constraint({"max_duration": 8}, "max_duration") == 8


def test_get_model_constraint_returns_default():
    assert get_model_constraint(None, "max_duration", 5) == 5
