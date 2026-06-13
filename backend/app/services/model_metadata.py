"""Canonical normalization and merge helpers for model cost/constraint metadata.

All provider-specific sync output is translated into a single set of canonical
keys so the rest of the application (cost estimator, planner context builder,
admin UI) can reason about models without knowing each provider's wire format.
"""

from __future__ import annotations

from typing import Any

CANONICAL_COST_KEYS = {
    "cost_per_image",
    "cost_per_second",
    "cost_per_1k_prompt_tokens",
    "cost_per_1k_completion_tokens",
    "currency",
}

CANONICAL_CONSTRAINT_KEYS = {
    "max_duration",
    "max_prompt_length",
    "max_resolution",
    "resolutions",
    "supported_aspect_ratios",
    "default_steps",
    "distilled",
    "size_param_family",
}


def normalize_cost_config(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert provider-specific cost fields to canonical keys."""
    if not raw:
        return None
    normalized: dict[str, Any] = {}
    key_map = {
        "compute_points": "cost_per_image",
        "compute_points_per_second": "cost_per_second",
        "credits_per_image": "cost_per_image",
        "credits_per_second": "cost_per_second",
        "price_per_image": "cost_per_image",
        "price_per_second": "cost_per_second",
    }
    for src, dst in key_map.items():
        if src in raw and dst not in raw:
            normalized[dst] = raw[src]
    for key in CANONICAL_COST_KEYS:
        if key in raw:
            normalized[key] = raw[key]
    # Preserve provider-specific extras.
    for key, value in raw.items():
        if key not in normalized:
            normalized[key] = value
    return normalized or None


def merge_cost_config(
    existing: dict[str, Any] | None,
    discovered: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge discovered cost config over existing; never wipe manually seeded prices."""
    if not existing and not discovered:
        return None
    base = dict(existing or {})
    norm = normalize_cost_config(discovered) or {}
    for key in CANONICAL_COST_KEYS:
        if key in norm and norm[key] not in (None, ""):
            base[key] = norm[key]
    for key, value in norm.items():
        if key not in CANONICAL_COST_KEYS and value not in (None, "", {}):
            base[key] = value
    return base or None


def merge_constraints(
    existing: dict[str, Any] | None,
    discovered: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge discovered constraints over existing, preserving unknown extras."""
    if not existing and not discovered:
        return None
    base = dict(existing or {})
    if discovered:
        for key in CANONICAL_CONSTRAINT_KEYS:
            if discovered.get(key) is not None:
                base[key] = discovered[key]
        for key, value in discovered.items():
            if key not in CANONICAL_CONSTRAINT_KEYS and value not in (None, "", []):
                base[key] = value
    return base or None


def merge_capabilities(
    existing: dict[str, Any] | None,
    discovered: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge discovered capability flags over existing."""
    if not existing and not discovered:
        return None
    base = dict(existing or {})
    if discovered:
        for key, value in discovered.items():
            if key.startswith(("accepts_", "outputs_")):
                base[key] = bool(value)
            elif value not in (None, ""):
                base[key] = value
    return base or None


def get_model_constraint(
    config: dict[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    """Read a constraint from either the top-level config dict or its constraints bucket."""
    if not config:
        return default
    constraints = config.get("constraints") or {}
    return config.get(key) if key in config else constraints.get(key, default)
