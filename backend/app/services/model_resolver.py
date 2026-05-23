"""Resolve model family + context → specific variant."""

from __future__ import annotations

_FAMILY_VARIANT_MAP: dict[str, dict[tuple[bool | str, bool], str]] = {
    "wan2.2": {
        (True, False): "wan2.2_i2v",
        (False, True): "wan2.2_s2v",
        (False, False): "wan2.2_t2v",
    },
    "ltx2.3": {
        (True, False): "ltx2.3_i2v",
        (False, False): "ltx2.3_t2v",
    },
    "ltx2.3-fast": {
        (False, False): "ltx2.3_distilled",
    },
}

_LEGACY_TO_FAMILY: dict[str, str] = {
    "wan2.2-t2v": "wan2.2",
    "wan2.2_t2v": "wan2.2",
    "wan2.2-s2v": "wan2.2",
    "wan2.2_s2v": "wan2.2",
    "wan2.2-i2v": "wan2.2",
    "wan2.2_i2v": "wan2.2",
    "ltx2.3-t2v": "ltx2.3",
    "ltx2.3_t2v": "ltx2.3",
    "ltx2.3-i2v": "ltx2.3",
    "ltx2.3_i2v": "ltx2.3",
    "ltx2.3-distilled": "ltx2.3-fast",
    "ltx2.3_distilled": "ltx2.3-fast",
}


class ModelResolutionError(ValueError):
    """Raised when a model family cannot be resolved to a variant."""

    pass


def resolve_model_variant(
    family_id: str,
    *,
    has_seed_image: bool = False,
    is_scene_continuation: bool = False,
) -> str:
    """Given a family ID and context, return the specific model variant ID.

    Args:
        family_id: User-selected model family (e.g., "wan2.2")
        has_seed_image: Whether a reference/seed image is available.
            Triggers I2V variants when supported.
        is_scene_continuation: Whether this is a scene continuation (S2V).
            Only relevant for WAN 2.2.

    Returns:
        Specific variant ID (e.g., "wan2.2_i2v")

    Raises:
        ModelResolutionError: If family_id is unknown or no valid variant exists
            for the given context.
    """
    family = get_family_from_legacy_id(family_id)
    variant_map = _FAMILY_VARIANT_MAP.get(family)
    if not variant_map:
        raise ModelResolutionError(f"Unknown model family: {family_id}")

    if family == "ltx2.3-fast":
        return variant_map[(False, False)]

    if is_scene_continuation:
        variant_id = variant_map.get((False, True))
        if variant_id:
            return variant_id

    if has_seed_image:
        variant_id = variant_map.get((True, False))
        if variant_id:
            return variant_id

    variant_id = variant_map.get((False, False))
    if variant_id:
        return variant_id

    raise ModelResolutionError(
        f"No valid variant for family={family} "
        f"(has_seed_image={has_seed_image}, is_scene_continuation={is_scene_continuation})"
    )


def get_family_from_legacy_id(variant_id: str) -> str:
    """Map old variant IDs to new family IDs for backward compatibility.

    Examples:
        "wan2.2-t2v" → "wan2.2"
        "wan2.2_t2v" → "wan2.2"
        "ltx2.3-t2v" → "ltx2.3"
        "ltx2.3-i2v" → "ltx2.3"

    If the input is already a family ID, it is returned unchanged.
    """
    return _LEGACY_TO_FAMILY.get(variant_id, variant_id)


def is_family_id(model_id: str) -> bool:
    """Check if a model ID is a family ID (not a legacy variant ID)."""
    return model_id in _FAMILY_VARIANT_MAP


def get_family_variants(family_id: str) -> dict[str, str]:
    """Get all variant IDs for a family.

    Returns a mapping of context label → variant ID, e.g.:
        {"i2v": "wan2.2_i2v", "t2v": "wan2.2_t2v", "s2v": "wan2.2_s2v"}
    """
    family = get_family_from_legacy_id(family_id)
    variant_map = _FAMILY_VARIANT_MAP.get(family)
    if not variant_map:
        return {}

    result: dict[str, str] = {}
    for (has_image, is_continuation), variant_id in variant_map.items():
        if has_image and is_continuation:
            label = "i2v+s2v"
        elif has_image:
            label = "i2v"
        elif is_continuation:
            label = "s2v"
        else:
            label = "t2v"
        result[label] = variant_id
    return result


def get_all_families() -> list[str]:
    """Return all supported family IDs."""
    return list(_FAMILY_VARIANT_MAP.keys())
