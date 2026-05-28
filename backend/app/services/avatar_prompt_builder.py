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

    return "\n".join(lines)
