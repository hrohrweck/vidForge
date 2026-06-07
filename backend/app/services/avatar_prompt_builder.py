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
