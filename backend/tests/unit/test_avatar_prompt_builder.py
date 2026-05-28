"""Unit tests for avatar prompt builder utility and planner integration."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.avatar_prompt_builder import build_avatar_context_string


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
