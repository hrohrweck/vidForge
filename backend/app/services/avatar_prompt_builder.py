"""Build avatar context strings for LLM prompts."""

from typing import Any


def build_avatar_context_string(avatars: list[dict[str, Any]]) -> str:
    """Format avatar data into a compact, readable text block for the LLM prompt.

    Args:
        avatars: List of resolved avatar dicts from enrich_inputs context.
                 Each dict has: name, gender, bio, role, consistency_strategy, etc.

    Returns:
        A formatted string like:
        AVATAR CAST:
        - Name: Alice | Gender: Female | Bio: A detective with 15 years on the force
          Role in this video: The investigating officer
        - Name: Bob | Gender: Male | Bio: A mysterious informant
          Role in this video: Alice's conflicted contact

    Returns empty string if avatars list is empty.
    """
    if not avatars:
        return ""

    lines = ["AVATAR CAST:"]
    for a in avatars:
        name = a.get("name", "Unknown")
        gender = a.get("gender", "")
        bio = a.get("bio", "")
        role = a.get("role", "")

        # Build the header line: Name | Gender | Bio
        header_parts = [f"Name: {name}"]
        if gender:
            header_parts.append(f"Gender: {gender}")
        if bio:
            header_parts.append(f"Bio: {bio}")
        lines.append(f"- {' | '.join(header_parts)}")

        # Role line (indented)
        if role:
            lines.append(f"  Role in this video: {role}")

        # Image reference info
        primary_path = a.get("primary_image_path", "")
        if primary_path:
            lines.append(f"  Image reference available: {primary_path}")

        # Consistency strategy (omit default "prompt_only")
        strategy = a.get("consistency_strategy", "")
        if strategy and strategy != "prompt_only":
            lines.append(f"  Visual consistency: uses {strategy} method")

    return "\n".join(lines)


def build_avatar_visual_context(avatars: list[dict[str, Any]]) -> str:
    """Return a concise visual summary for model-capabilities context.

    Args:
        avatars: List of resolved avatar dicts (same shape as
                 build_avatar_context_string).

    Returns:
        A formatted string like:

        CHARACTER REFERENCES:
        - Alice: reference image at /path/to/alice.png (strategy: ip_adapter)
        - Bob: reference image at /path/to/bob.png (strategy: face_swap)
        - Carol: no reference image (strategy: prompt_only)

    Returns empty string if avatars list is empty.
    """
    if not avatars:
        return ""

    lines = ["CHARACTER REFERENCES:"]
    for a in avatars:
        name = a.get("name", "Unknown")
        img = a.get("primary_image_path", "")
        strategy = a.get("consistency_strategy", "prompt_only") or "prompt_only"

        if img:
            lines.append(
                f"- {name}: reference image at {img} (strategy: {strategy})"
            )
        else:
            lines.append(
                f"- {name}: no reference image (strategy: {strategy})"
            )

    return "\n".join(lines)


def build_object_catalog_string(objects: list[dict[str, Any]]) -> str:
    """Format object catalog data into a compact text block for the LLM prompt.

    Args:
        objects: List of object dicts from context["objects"].
                 Each dict has: name, description, visual_properties (dict),
                 role, importance_score.

    Returns:
        A formatted string like:
        OBJECT CATALOG (no reference images yet — planner decides which need them):
        - Object: sports car | Category: vehicle
          Description: Red Ferrari F40, low profile, racing stripes
          Visual properties: color=red, make=Ferrari, model=F40
          Role: protagonist's vehicle

    Returns empty string if objects list is empty.
    """
    if not objects:
        return ""

    lines = [
        "OBJECT CATALOG (no reference images yet — planner decides which need them):"
    ]
    for obj in objects[:10]:
        name = obj.get("name", "Unknown")
        category = obj.get("category", "")
        description = obj.get("description", "")
        visual_properties = obj.get("visual_properties") or {}
        role = obj.get("role", "")

        header_parts = [f"Object: {name}"]
        if category:
            header_parts.append(f"Category: {category}")
        lines.append(f"- {' | '.join(header_parts)}")

        if description:
            lines.append(f"  Description: {description}")

        if visual_properties:
            props_str = ", ".join(
                f"{k}={v}" for k, v in visual_properties.items()
            )
            lines.append(f"  Visual properties: {props_str}")

        if role:
            lines.append(f"  Role: {role}")

    return "\n".join(lines)


def build_combined_context(
    avatars: list[dict[str, Any]], objects: list[dict[str, Any]]
) -> str:
    """Combine avatar cast and object catalog into a single context string.

    Args:
        avatars: List of resolved avatar dicts.
        objects: List of resolved object dicts.

    Returns:
        Combined output with clear section breaks. Empty sections are omitted.
    """
    avatar_section = build_avatar_context_string(avatars)
    object_section = build_object_catalog_string(objects)

    sections = []
    if avatar_section:
        sections.append(avatar_section)
    if object_section:
        sections.append(object_section)

    return "\n\n".join(sections)
