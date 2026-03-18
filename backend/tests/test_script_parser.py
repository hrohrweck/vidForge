import pytest
from app.services.script_parser import ScriptParser, parse_script


def test_parse_simple_script():
    parser = ScriptParser()
    script = "Welcome to our video. [Show a beautiful sunset] Today we explore nature."

    result = parser.parse(script)

    assert len(result.narration_segments) == 2
    assert len(result.visual_cues) == 1
    assert result.visual_cues[0].annotation == "Show a beautiful sunset"


def test_parse_multiple_annotations():
    parser = ScriptParser()
    script = "First narration. [Scene 1] Second narration. [Scene 2] Third narration."

    result = parser.parse(script)

    assert len(result.visual_cues) == 2
    assert result.visual_cues[0].annotation == "Scene 1"
    assert result.visual_cues[1].annotation == "Scene 2"


def test_extract_narration_text():
    parser = ScriptParser()
    script = "Pure narration here. [Visual annotation] More narration."

    text = parser.extract_narration_text(script)

    assert "Pure narration here" in text
    assert "More narration" in text
    assert "[Visual annotation]" not in text
    assert "Visual annotation" not in text


def test_extract_annotations():
    parser = ScriptParser()
    script = "Text [First] more [Second] end [Third]."

    annotations = parser.extract_annotations(script)

    assert len(annotations) == 3
    assert annotations == ["First", "Second", "Third"]


def test_get_scene_descriptions():
    parser = ScriptParser()
    script = "Intro text. [Scene: A forest] Middle narration. [Scene: An ocean] Outro."

    result = parser.parse(script)
    scenes = parser.get_scene_descriptions(result)

    assert len(scenes) == 2
    assert scenes[0]["visual_description"] == "Scene: A forest"
    assert scenes[1]["visual_description"] == "Scene: An ocean"


def test_empty_script():
    parser = ScriptParser()
    result = parser.parse("")

    assert len(result.narration_segments) == 0
    assert len(result.visual_cues) == 0


def test_no_annotations():
    parser = ScriptParser()
    script = "Just plain narration without any annotations."

    result = parser.parse(script)

    assert len(result.visual_cues) == 0
    assert len(result.narration_segments) == 1


def test_convenience_function():
    script = "Test [Annotation] end."
    result = parse_script(script)

    assert len(result.visual_cues) == 1
    assert result.visual_cues[0].annotation == "Annotation"
