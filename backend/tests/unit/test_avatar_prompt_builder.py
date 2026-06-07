"""Unit tests for avatar prompt builder utility and planner integration."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.avatar_prompt_builder import (
    build_avatar_context_string,
    build_avatar_visual_context,
    build_object_catalog_string,
    build_combined_context,
)


# ---------------------------------------------------------------------------
# build_avatar_context_string unit tests
# ---------------------------------------------------------------------------

AVATAR_FULL = {
    "name": "Alice",
    "gender": "Female",
    "bio": "A detective with 15 years on the force",
    "role": "The investigating officer",
}

AVATAR_NO_BIO = {
    "name": "Bob",
    "gender": "Male",
    "bio": None,
    "role": "Informant",
}

AVATAR_NO_ROLE = {
    "name": "Carol",
    "gender": "Non-binary",
    "bio": "A hacker with a mysterious past",
    "role": None,
}

AVATAR_NO_BIO_NO_ROLE = {
    "name": "Dave",
    "gender": "Male",
    "bio": None,
    "role": None,
}


def test_build_single_avatar_full_fields():
    """Full avatar dict produces complete formatted lines."""
    result = build_avatar_context_string([AVATAR_FULL])

    lines = result.split("\n")
    assert lines[0] == "AVATAR CAST:"
    assert len(lines) == 3  # header + bullet + role

    bullet = lines[1]
    assert bullet.startswith("- ")
    assert "Name: Alice" in bullet
    assert "Gender: Female" in bullet
    assert "Bio: A detective with 15 years on the force" in bullet

    role_line = lines[2]
    assert "Role in this video: The investigating officer" in role_line
    assert role_line.startswith("  ")


def test_build_multiple_avatars():
    """Two avatars → each on its own line pair."""
    avatars = [
        {"name": "Alice", "gender": "Female", "bio": "Detective", "role": "Lead"},
        {"name": "Bob", "gender": "Male", "bio": "Suspect", "role": "Supporting"},
    ]
    result = build_avatar_context_string(avatars)

    lines = result.split("\n")
    assert lines[0] == "AVATAR CAST:"
    # Alice: bullet + role
    assert "Name: Alice" in lines[1]
    assert "Role in this video: Lead" in lines[2]
    # Bob: bullet + role
    assert "Name: Bob" in lines[3]
    assert "Role in this video: Supporting" in lines[4]


def test_build_missing_bio():
    """bio=None/empty → no 'Bio:' substring in output."""
    result = build_avatar_context_string([AVATAR_NO_BIO])
    assert "Bio:" not in result
    assert "Name: Bob" in result
    assert "Gender: Male" in result


def test_build_missing_bio_empty_string():
    """bio='' → same as None, no Bio line."""
    avatar = {"name": "Eve", "gender": "Female", "bio": "", "role": "Extra"}
    result = build_avatar_context_string([avatar])
    assert "Bio:" not in result


def test_build_missing_role():
    """role=None → no 'Role in this video:' line."""
    result = build_avatar_context_string([AVATAR_NO_ROLE])
    assert "Role in this video:" not in result
    assert "Name: Carol" in result


def test_build_missing_role_empty_string():
    """role='' → same as None, no role line."""
    avatar = {"name": "Frank", "gender": "Male", "bio": "Bystander", "role": ""}
    result = build_avatar_context_string([avatar])
    assert "Role in this video:" not in result


def test_build_no_bio_no_role():
    """Avatar with neither bio nor role → single bullet line, no extra lines."""
    result = build_avatar_context_string([AVATAR_NO_BIO_NO_ROLE])

    lines = result.split("\n")
    assert len(lines) == 2  # header + bullet only
    assert "Name: Dave" in lines[1]
    assert "Bio:" not in lines[1]
    assert "Role" not in lines[1]


def test_build_empty_list():
    """Empty list → empty string."""
    result = build_avatar_context_string([])
    assert result == ""


def test_build_output_structure():
    """Output always starts with 'AVATAR CAST:' header and uses bullet points."""
    avatars = [
        {"name": "X", "gender": "Y", "bio": "Z", "role": "R"},
    ]
    result = build_avatar_context_string(avatars)

    assert result.startswith("AVATAR CAST:")
    assert "\n- " in result  # bullet points present


def test_build_output_length():
    """5 avatars with full bios → output stays compact (linear scaling)."""
    avatars = [
        {
            "name": f"C{i}",
            "gender": "Unknown",
            "bio": "A short bio for character.",
            "role": f"Role {i}",
        }
        for i in range(5)
    ]
    result = build_avatar_context_string(avatars)
    # Each avatar adds roughly 50-60 chars; 5 should stay well under 500
    assert len(result) < 500


def test_build_gender_missing():
    """gender=None/empty → Gender omitted from bullet line."""
    avatar = {"name": "NoGender", "gender": "", "bio": "Test", "role": "Test"}
    result = build_avatar_context_string([avatar])
    assert "Gender:" not in result


def test_build_name_fallback():
    """name missing → 'Unknown' fallback."""
    avatar = {"gender": "Male", "bio": "Mystery", "role": "Enigma"}
    result = build_avatar_context_string([avatar])
    assert "Name: Unknown" in result


# ---------------------------------------------------------------------------
# Planner integration tests — verify avatars_context wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_to_video_planner_accepts_context():
    """plan_scenes_from_prompt signature includes avatars_context param."""
    from plugins.prompt_to_video.planner import plan_scenes_from_prompt
    import inspect

    sig = inspect.signature(plan_scenes_from_prompt)
    assert "avatars_context" in sig.parameters
    param = sig.parameters["avatars_context"]
    # Default should be None
    assert param.default is None


@pytest.mark.asyncio
async def test_script_to_video_planner_accepts_context():
    """plan_scenes_from_script signature includes avatars_context param."""
    from plugins.script_to_video.planner import plan_scenes_from_script
    import inspect

    sig = inspect.signature(plan_scenes_from_script)
    assert "avatars_context" in sig.parameters
    param = sig.parameters["avatars_context"]
    assert param.default is None


@pytest.mark.asyncio
async def test_planner_includes_context_in_prompt():
    """When avatars_context is provided, the LLM prompt contains it."""
    avatar_ctx = build_avatar_context_string([AVATAR_FULL])

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A detective story",
            duration=10,
            avatars_context=avatar_ctx,
        )

    # Verify LLM.generate was called with avatar context in the prompt
    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "AVATAR CAST:" in prompt_text
    assert "Name: Alice" in prompt_text


@pytest.mark.asyncio
async def test_planner_no_avatar_context_omits_section():
    """When avatars_context is None, prompt does NOT contain AVATAR CAST."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A simple story",
            duration=10,
            avatars_context=None,
        )

    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "AVATAR CAST:" not in prompt_text
    assert "A simple story" in prompt_text


@pytest.mark.asyncio
async def test_script_planner_includes_context_in_prompt():
    """script_to_video planner also includes avatar context when provided."""
    avatar_ctx = build_avatar_context_string([AVATAR_FULL])

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.script_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.script_to_video.planner import plan_scenes_from_script

        await plan_scenes_from_script(
            segments=[{"narration": "Once upon a time..."}],
            duration=30,
            avatars_context=avatar_ctx,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "AVATAR CAST:" in prompt_text
    assert "Name: Alice" in prompt_text


@pytest.mark.asyncio
async def test_script_planner_no_avatar_context_omits_section():
    """script_to_video planner with None context omits AVATAR CAST."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.script_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.script_to_video.planner import plan_scenes_from_script

        await plan_scenes_from_script(
            segments=[{"narration": "No avatars here"}],
            duration=30,
            avatars_context=None,
        )

    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "AVATAR CAST:" not in prompt_text
    assert "No avatars here" in prompt_text


# ---------------------------------------------------------------------------
# Enhanced context tests — image references and consistency strategy
# ---------------------------------------------------------------------------


def test_build_context_with_image_reference():
    """When primary_image_path set, output includes 'Image reference available'."""
    avatar = {
        "name": "Alice",
        "gender": "Female",
        "bio": "Detective",
        "role": "Lead",
        "primary_image_path": "/avatars/alice.png",
    }
    result = build_avatar_context_string([avatar])
    assert "Image reference available: /avatars/alice.png" in result


def test_build_context_without_image_reference():
    """When primary_image_path is empty, no image line in output."""
    avatar = {
        "name": "Bob",
        "gender": "Male",
        "bio": "Suspect",
        "role": "Supporting",
    }
    result = build_avatar_context_string([avatar])
    assert "Image reference available" not in result


def test_build_context_with_consistency_strategy():
    """Non-default consistency strategy appears in output."""
    avatar = {
        "name": "Carol",
        "gender": "Female",
        "bio": "Hacker",
        "role": "Lead",
        "consistency_strategy": "lora",
    }
    result = build_avatar_context_string([avatar])
    assert "Visual consistency: uses lora method" in result


def test_build_context_omits_prompt_only_strategy():
    """Default prompt_only strategy is omitted from output."""
    avatar = {
        "name": "Dave",
        "gender": "Male",
        "bio": "Extra",
        "role": "Background",
        "consistency_strategy": "prompt_only",
    }
    result = build_avatar_context_string([avatar])
    assert "Visual consistency" not in result


def test_build_context_with_image_and_strategy():
    """Both image reference and non-default strategy present."""
    avatar = {
        "name": "Eve",
        "gender": "Female",
        "bio": "Spy",
        "role": "Lead",
        "primary_image_path": "/avatars/eve.png",
        "consistency_strategy": "ip_adapter",
    }
    result = build_avatar_context_string([avatar])
    assert "Image reference available: /avatars/eve.png" in result
    assert "Visual consistency: uses ip_adapter method" in result


def test_build_context_empty_strategy():
    """Empty consistency_strategy treated same as prompt_only (omitted)."""
    avatar = {
        "name": "Frank",
        "gender": "Male",
        "bio": "Drifter",
        "role": "Extra",
        "consistency_strategy": "",
    }
    result = build_avatar_context_string([avatar])
    assert "Visual consistency" not in result


# ---------------------------------------------------------------------------
# build_avatar_visual_context tests
# ---------------------------------------------------------------------------


def test_visual_context_single_with_image():
    """Single avatar with image ref produces correct line."""
    avatars = [
        {
            "name": "Alice",
            "primary_image_path": "/avatars/alice.png",
            "consistency_strategy": "ip_adapter",
        }
    ]
    result = build_avatar_visual_context(avatars)
    assert result.startswith("CHARACTER REFERENCES:")
    assert "Alice: reference image at /avatars/alice.png" in result
    assert "strategy: ip_adapter" in result


def test_visual_context_single_no_image():
    """Single avatar without image ref shows 'no reference image'."""
    avatars = [
        {
            "name": "Bob",
            "consistency_strategy": "prompt_only",
        }
    ]
    result = build_avatar_visual_context(avatars)
    assert "Bob: no reference image (strategy: prompt_only)" in result


def test_visual_context_multiple():
    """Multiple avatars each get their own line."""
    avatars = [
        {
            "name": "Alice",
            "primary_image_path": "/avatars/alice.png",
            "consistency_strategy": "face_swap",
        },
        {
            "name": "Bob",
            "consistency_strategy": "prompt_only",
        },
    ]
    result = build_avatar_visual_context(avatars)
    assert "Alice: reference image at /avatars/alice.png (strategy: face_swap)" in result
    assert "Bob: no reference image (strategy: prompt_only)" in result


def test_visual_context_empty():
    """Empty list returns empty string."""
    assert build_avatar_visual_context([]) == ""


def test_visual_context_no_name_fallback():
    """Missing name uses 'Unknown' fallback."""
    avatars = [
        {
            "primary_image_path": "/imgs/someone.png",
            "consistency_strategy": "lora",
        }
    ]
    result = build_avatar_visual_context(avatars)
    assert "Unknown: reference image at /imgs/someone.png" in result


# ---------------------------------------------------------------------------
# Model capabilities context in scene planner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_to_video_planner_accepts_model_capabilities():
    """plan_scenes_from_prompt signature includes model_capabilities_context param."""
    from plugins.prompt_to_video.planner import plan_scenes_from_prompt
    import inspect

    sig = inspect.signature(plan_scenes_from_prompt)
    assert "model_capabilities_context" in sig.parameters
    param = sig.parameters["model_capabilities_context"]
    assert param.default is None


@pytest.mark.asyncio
async def test_planner_includes_model_capabilities_in_prompt():
    """When model_capabilities_context is provided, the LLM prompt contains it."""
    caps_ctx = (
        "VIDEO MODEL CAPABILITIES:\n"
        "  Model: wan2.2\n"
        "  Generation type: text_to_video (text prompt only → video)\n\n"
        "IMAGE MODEL CAPABILITIES:\n"
        "  Model: flux1-schnell\n"
        "  Generation type: text_to_image (text prompt only — no reference image needed)\n"
    )

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A sci-fi story",
            duration=10,
            model_capabilities_context=caps_ctx,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "VIDEO MODEL CAPABILITIES:" in prompt_text
    assert "IMAGE MODEL CAPABILITIES:" in prompt_text
    assert "wan2.2" in prompt_text
    assert "flux1-schnell" in prompt_text


@pytest.mark.asyncio
async def test_planner_none_model_capabilities_omits_block():
    """When model_capabilities_context is None, prompt does NOT contain CAPABILITIES block."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A simple story",
            duration=10,
            model_capabilities_context=None,
        )

    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "VIDEO MODEL CAPABILITIES:" not in prompt_text
    assert "IMAGE MODEL CAPABILITIES:" not in prompt_text
    assert "A simple story" in prompt_text


def test_system_prompt_contains_story_arc():
    """SYSTEM_PROMPT includes story arc structure and consistency rules."""
    from plugins.prompt_to_video.planner import SYSTEM_PROMPT

    assert "STORY ARC" in SYSTEM_PROMPT
    assert "Opening" in SYSTEM_PROMPT
    assert "Development" in SYSTEM_PROMPT
    assert "Climax" in SYSTEM_PROMPT
    assert "Resolution" in SYSTEM_PROMPT
    assert "CONSISTENCY RULES:" in SYSTEM_PROMPT
    assert "consistent visual description" in SYSTEM_PROMPT
    assert "Color palette" in SYSTEM_PROMPT


def test_system_prompt_contains_model_guidance():
    """SYSTEM_PROMPT includes MODEL GUIDANCE for adapting to capabilities."""
    from plugins.prompt_to_video.planner import SYSTEM_PROMPT

    assert "MODEL GUIDANCE:" in SYSTEM_PROMPT
    assert "seed images" in SYSTEM_PROMPT
    assert "seed_image_prompt" in SYSTEM_PROMPT
    assert "start+end frames" in SYSTEM_PROMPT


def test_system_prompt_retains_avatar_instructions():
    """SYSTEM_PROMPT still contains the original avatar cast instructions."""
    from plugins.prompt_to_video.planner import SYSTEM_PROMPT

    assert "AVATAR CAST MEMBERS:" in SYSTEM_PROMPT
    assert "Only use avatars that are provided" in SYSTEM_PROMPT
    assert "do NOT invent new characters" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Script-to-Video planner — model capabilities context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_to_video_planner_accepts_model_capabilities():
    """plan_scenes_from_script signature includes model_capabilities_context param."""
    from plugins.script_to_video.planner import plan_scenes_from_script
    import inspect

    sig = inspect.signature(plan_scenes_from_script)
    assert "model_capabilities_context" in sig.parameters
    param = sig.parameters["model_capabilities_context"]
    assert param.default is None


@pytest.mark.asyncio
async def test_script_planner_includes_model_capabilities_in_prompt():
    """When model_capabilities_context is provided, the LLM prompt contains it."""
    caps_ctx = (
        "VIDEO MODEL CAPABILITIES:\n"
        "  Model: wan2.2\n"
        "  Generation type: text_to_video (text prompt only → video)\n\n"
        "IMAGE MODEL CAPABILITIES:\n"
        "  Model: flux1-schnell\n"
        "  Generation type: text_to_image (text prompt only — no reference image needed)\n"
    )

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.script_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.script_to_video.planner import plan_scenes_from_script

        await plan_scenes_from_script(
            segments=[{"narration": "A sci-fi story segment"}],
            duration=30,
            model_capabilities_context=caps_ctx,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "VIDEO MODEL CAPABILITIES:" in prompt_text
    assert "IMAGE MODEL CAPABILITIES:" in prompt_text
    assert "wan2.2" in prompt_text
    assert "flux1-schnell" in prompt_text


@pytest.mark.asyncio
async def test_script_planner_none_model_capabilities_omits_block():
    """When model_capabilities_context is None, prompt does NOT contain CAPABILITIES block."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.script_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.script_to_video.planner import plan_scenes_from_script

        await plan_scenes_from_script(
            segments=[{"narration": "A simple story segment"}],
            duration=30,
            model_capabilities_context=None,
        )

    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "VIDEO MODEL CAPABILITIES:" not in prompt_text
    assert "IMAGE MODEL CAPABILITIES:" not in prompt_text
    assert "A simple story segment" in prompt_text


def test_script_system_prompt_contains_story_arc():
    """script_to_video SYSTEM_PROMPT includes story arc structure and consistency rules."""
    from plugins.script_to_video.planner import SYSTEM_PROMPT

    assert "STORY ARC" in SYSTEM_PROMPT
    assert "Opening" in SYSTEM_PROMPT
    assert "Development" in SYSTEM_PROMPT
    assert "Climax" in SYSTEM_PROMPT
    assert "Resolution" in SYSTEM_PROMPT
    assert "CONSISTENCY RULES:" in SYSTEM_PROMPT
    assert "consistent visual description" in SYSTEM_PROMPT
    assert "Color palette" in SYSTEM_PROMPT


def test_script_system_prompt_contains_model_guidance():
    """script_to_video SYSTEM_PROMPT includes MODEL GUIDANCE for adapting to capabilities."""
    from plugins.script_to_video.planner import SYSTEM_PROMPT

    assert "MODEL GUIDANCE:" in SYSTEM_PROMPT
    assert "seed images" in SYSTEM_PROMPT
    assert "seed_image_prompt" in SYSTEM_PROMPT
    assert "start+end frames" in SYSTEM_PROMPT


def test_script_system_prompt_retains_narration():
    """script_to_video SYSTEM_PROMPT still contains narration-specific instructions."""
    from plugins.script_to_video.planner import SYSTEM_PROMPT

    assert "narration" in SYSTEM_PROMPT
    assert "Narration is the text that will be spoken" in SYSTEM_PROMPT
    assert "AVATAR CAST MEMBERS:" in SYSTEM_PROMPT
    assert "Only use avatars that are provided" in SYSTEM_PROMPT


OBJECT_FULL = {
    "name": "sports car",
    "category": "vehicle",
    "description": "Red Ferrari F40, low profile, racing stripes",
    "visual_properties": {"color": "red", "make": "Ferrari", "model": "F40"},
    "role": "protagonist's vehicle",
    "importance_score": 0.9,
}

OBJECT_MINIMAL = {
    "name": "wristwatch",
    "category": "accessory",
    "description": "Silver chronograph with leather strap",
    "visual_properties": {"color": "silver", "material": "leather"},
    "role": "worn by detective in office scenes",
    "importance_score": 0.5,
}


def test_build_object_catalog_two_objects():
    """Two objects produce correct formatted output."""
    result = build_object_catalog_string([OBJECT_FULL, OBJECT_MINIMAL])

    lines = result.split("\n")
    assert lines[0] == (
        "OBJECT CATALOG (no reference images yet — planner decides which need them):"
    )

    assert "- Object: sports car | Category: vehicle" in result
    assert "Description: Red Ferrari F40, low profile, racing stripes" in result
    assert "Visual properties: color=red, make=Ferrari, model=F40" in result
    assert "Role: protagonist's vehicle" in result

    assert "- Object: wristwatch | Category: accessory" in result
    assert "Description: Silver chronograph with leather strap" in result
    assert "Visual properties: color=silver, material=leather" in result
    assert "Role: worn by detective in office scenes" in result


def test_build_object_catalog_empty_list():
    """Empty list returns empty string."""
    result = build_object_catalog_string([])
    assert result == ""


def test_build_object_catalog_with_visual_properties():
    """Object with visual_properties displays them as key=value pairs."""
    result = build_object_catalog_string([OBJECT_FULL])
    assert "Visual properties: color=red, make=Ferrari, model=F40" in result


def test_build_object_catalog_without_visual_properties():
    """Object missing visual_properties gracefully handled."""
    obj = {
        "name": "mystery box",
        "category": "prop",
        "description": "A plain wooden crate",
        "role": "clue in scene 3",
    }
    result = build_object_catalog_string([obj])
    assert "Visual properties" not in result
    assert "- Object: mystery box | Category: prop" in result
    assert "Description: A plain wooden crate" in result
    assert "Role: clue in scene 3" in result


def test_build_object_catalog_missing_optional_fields():
    """Object with only name produces minimal output."""
    obj = {"name": "orb"}
    result = build_object_catalog_string([obj])
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[1] == "- Object: orb"


def test_build_object_catalog_caps_at_ten():
    """More than 10 objects are capped at 10."""
    objects = [{"name": f"obj{i}"} for i in range(15)]
    result = build_object_catalog_string(objects)
    bullet_count = result.count("\n- ")
    assert bullet_count == 10


def test_build_combined_context_both_sections():
    """Both avatars and objects present → both sections with clear break."""
    avatars = [AVATAR_FULL]
    objects = [OBJECT_FULL]
    result = build_combined_context(avatars, objects)

    assert "AVATAR CAST:" in result
    assert "OBJECT CATALOG" in result
    assert "\n\n" in result


def test_build_combined_context_only_avatars():
    """Only avatars → avatar section only, no object catalog."""
    result = build_combined_context([AVATAR_FULL], [])
    assert "AVATAR CAST:" in result
    assert "OBJECT CATALOG" not in result


def test_build_combined_context_only_objects():
    """Only objects → object catalog only, no avatar cast."""
    result = build_combined_context([], [OBJECT_FULL])
    assert "OBJECT CATALOG" in result
    assert "AVATAR CAST:" not in result


def test_build_combined_context_empty():
    """Both empty → empty string."""
    result = build_combined_context([], [])
    assert result == ""


# ---------------------------------------------------------------------------
# Object planner tests — object priority rules, context passing, parsing
# ---------------------------------------------------------------------------


OBJECTS_CTX = """OBJECT CATALOG (no reference images yet — planner decides which need them):
- Object: sports car | Category: vehicle
  Description: Red Ferrari F40, low profile, racing stripes
  Visual properties: color=red, make=Ferrari, model=F40
  Role: protagonist's vehicle"""

REFCAP_CTX = """REFERENCE CAPACITY: This video model accepts up to 2 reference images per scene.
1 slot is consumed by character avatars. 1 slot remains for objects.

PRIORITY RULE: Rank objects by narrative importance. The top 1 object will receive reference images. Remaining objects must be described in words."""


def test_system_prompt_contains_object_priority_rules():
    """SYSTEM_PROMPT includes OBJECT PRIORITY RULES for ranking and selecting objects."""
    from plugins.prompt_to_video.planner import SYSTEM_PROMPT

    assert "OBJECT PRIORITY RULES:" in SYSTEM_PROMPT
    assert "Critical (score 0.8-1.0)" in SYSTEM_PROMPT
    assert "Important (score 0.5-0.7)" in SYSTEM_PROMPT
    assert "Incidental (score 0.1-0.4)" in SYSTEM_PROMPT
    assert "object_selections" in SYSTEM_PROMPT
    assert "OBJECT CONSISTENCY:" in SYSTEM_PROMPT
    assert "NEVER change them across scenes" in SYSTEM_PROMPT


def test_script_system_prompt_contains_object_priority_rules():
    """script_to_video SYSTEM_PROMPT also includes OBJECT PRIORITY RULES."""
    from plugins.script_to_video.planner import SYSTEM_PROMPT

    assert "OBJECT PRIORITY RULES:" in SYSTEM_PROMPT
    assert "Critical (score 0.8-1.0)" in SYSTEM_PROMPT
    assert "object_selections" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_object_planner_prompt_to_video_accepts_params():
    """plan_scenes_from_prompt signature includes objects_context and reference_capacity_context."""
    from plugins.prompt_to_video.planner import plan_scenes_from_prompt
    import inspect

    sig = inspect.signature(plan_scenes_from_prompt)
    assert "objects_context" in sig.parameters
    assert "reference_capacity_context" in sig.parameters
    assert sig.parameters["objects_context"].default is None
    assert sig.parameters["reference_capacity_context"].default is None


@pytest.mark.asyncio
async def test_object_planner_script_to_video_accepts_params():
    """plan_scenes_from_script signature includes objects_context and reference_capacity_context."""
    from plugins.script_to_video.planner import plan_scenes_from_script
    import inspect

    sig = inspect.signature(plan_scenes_from_script)
    assert "objects_context" in sig.parameters
    assert "reference_capacity_context" in sig.parameters
    assert sig.parameters["objects_context"].default is None
    assert sig.parameters["reference_capacity_context"].default is None


@pytest.mark.asyncio
async def test_object_planner_includes_objects_context_in_prompt():
    """When objects_context is provided, the LLM prompt contains it."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}], '
        '"object_selections": []}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A car chase story",
            duration=10,
            objects_context=OBJECTS_CTX,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "OBJECT CATALOG" in prompt_text
    assert "sports car" in prompt_text
    assert "Ferrari" in prompt_text


@pytest.mark.asyncio
async def test_object_planner_includes_reference_capacity_in_prompt():
    """When reference_capacity_context is provided, the LLM prompt contains it."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}], '
        '"object_selections": []}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A car chase story",
            duration=10,
            reference_capacity_context=REFCAP_CTX,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "REFERENCE CAPACITY" in prompt_text
    assert "PRIORITY RULE" in prompt_text


@pytest.mark.asyncio
async def test_object_planner_none_contexts_omitted():
    """When both new contexts are None, prompt does NOT contain them."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.prompt_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.prompt_to_video.planner import plan_scenes_from_prompt

        await plan_scenes_from_prompt(
            prompt="A simple story",
            duration=10,
            objects_context=None,
            reference_capacity_context=None,
        )

    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "OBJECT CATALOG" not in prompt_text
    assert "REFERENCE CAPACITY" not in prompt_text
    assert "A simple story" in prompt_text


def test_object_planner_parse_response_extracts_object_selections():
    """_parse_response extracts object_selections from valid JSON response."""
    from plugins.prompt_to_video.planner import _parse_response

    response = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "car chase", "image_prompt": "car chase img", '
        '"mood": "intense", "camera_movement": "pan_right"}], '
        '"object_selections": [{"object_name": "sports car", '
        '"importance_score": 0.9, '
        '"seed_image_prompt": "Red Ferrari F40 on highway", '
        '"scenes": [1]}]}'
    )

    result = _parse_response(response, 5.0)
    assert "scenes" in result
    assert "object_selections" in result
    assert len(result["scenes"]) == 1
    assert len(result["object_selections"]) == 1
    obj = result["object_selections"][0]
    assert obj["object_name"] == "sports car"
    assert obj["importance_score"] == 0.9
    assert obj["seed_image_prompt"] == "Red Ferrari F40 on highway"
    assert obj["scenes"] == [1]


def test_object_planner_parse_response_empty_object_selections():
    """_parse_response returns empty object_selections when not in JSON."""
    from plugins.prompt_to_video.planner import _parse_response

    response = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"visual_description": "test", "image_prompt": "test", '
        '"mood": "neutral", "camera_movement": "static"}]}'
    )

    result = _parse_response(response, 5.0)
    assert "scenes" in result
    assert "object_selections" in result
    assert result["object_selections"] == []


def test_object_planner_fallback_contains_empty_selections():
    """_fallback_result returns scenes and empty object_selections."""
    from plugins.prompt_to_video.planner import _fallback_result

    result = _fallback_result(10.0)
    assert "scenes" in result
    assert "object_selections" in result
    assert result["object_selections"] == []
    assert len(result["scenes"]) > 0


@pytest.mark.asyncio
async def test_object_planner_script_planner_includes_contexts_in_prompt():
    """script_to_video planner also includes objects and capacity contexts."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}], '
        '"object_selections": []}'
    )
    mock_llm.close = AsyncMock()

    with patch(
        "plugins.script_to_video.planner.LLMClient",
        return_value=mock_llm,
    ):
        from plugins.script_to_video.planner import plan_scenes_from_script

        await plan_scenes_from_script(
            segments=[{"narration": "A car chase scene"}],
            duration=30,
            objects_context=OBJECTS_CTX,
            reference_capacity_context=REFCAP_CTX,
        )

    mock_llm.generate.assert_called_once()
    call_kwargs = mock_llm.generate.call_args.kwargs
    prompt_text = call_kwargs["prompt"]
    assert "OBJECT CATALOG" in prompt_text
    assert "REFERENCE CAPACITY" in prompt_text
    assert "sports car" in prompt_text
    assert "PRIORITY RULE" in prompt_text


def test_object_planner_script_parse_extracts_object_selections():
    """script_to_video _parse_response also extracts object_selections."""
    from plugins.script_to_video.planner import _parse_response

    response = (
        '{"scenes": [{"start_time": 0, "end_time": 5, '
        '"narration": "test", "visual_description": "test", '
        '"image_prompt": "test", "mood": "neutral", "camera_movement": "static"}], '
        '"object_selections": [{"object_name": "wristwatch", '
        '"importance_score": 0.6, '
        '"seed_image_prompt": "Silver chronograph on detective desk", '
        '"scenes": [1, 2]}]}'
    )

    result = _parse_response(response, 5.0)
    assert "object_selections" in result
    assert len(result["object_selections"]) == 1
    obj = result["object_selections"][0]
    assert obj["object_name"] == "wristwatch"
    assert obj["importance_score"] == 0.6
    assert obj["scenes"] == [1, 2]


def test_object_planner_script_fallback_contains_empty_selections():
    """script_to_video _fallback_result returns empty object_selections."""
    from plugins.script_to_video.planner import _fallback_result

    result = _fallback_result(3)
    assert "scenes" in result
    assert "object_selections" in result
    assert result["object_selections"] == []
    assert len(result["scenes"]) == 3
