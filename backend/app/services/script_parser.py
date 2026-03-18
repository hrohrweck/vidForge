import re
from dataclasses import dataclass
from typing import List


@dataclass
class NarrationSegment:
    text: str
    start_index: int
    end_index: int


@dataclass
class VisualCue:
    annotation: str
    start_index: int
    end_index: int
    preceding_narration: str | None = None


@dataclass
class ParsedScript:
    narration_segments: List[NarrationSegment]
    visual_cues: List[VisualCue]
    raw_text: str


class ScriptParser:
    """
    Parser for scripts with revid.ai-compatible annotations.

    Supports bracketed annotations like:
    "This is narration. [Show a sunset over mountains] More narration here."
    """

    ANNOTATION_PATTERN = re.compile(r"\[([^\]]+)\]")

    def parse(self, script: str) -> ParsedScript:
        narration_segments = []
        visual_cues = []

        last_end = 0
        annotation_matches = list(self.ANNOTATION_PATTERN.finditer(script))

        for i, match in enumerate(annotation_matches):
            narration_text = script[last_end : match.start()].strip()

            if narration_text:
                narration_segments.append(
                    NarrationSegment(
                        text=narration_text,
                        start_index=last_end,
                        end_index=match.start(),
                    )
                )

            visual_cues.append(
                VisualCue(
                    annotation=match.group(1).strip(),
                    start_index=match.start(),
                    end_index=match.end(),
                    preceding_narration=narration_text if narration_text else None,
                )
            )

            last_end = match.end()

        final_narration = script[last_end:].strip()
        if final_narration:
            narration_segments.append(
                NarrationSegment(
                    text=final_narration,
                    start_index=last_end,
                    end_index=len(script),
                )
            )

        return ParsedScript(
            narration_segments=narration_segments,
            visual_cues=visual_cues,
            raw_text=script,
        )

    def extract_narration_text(self, script: str) -> str:
        """Extract only the narration text, removing annotations."""
        return self.ANNOTATION_PATTERN.sub("", script).strip()

    def extract_annotations(self, script: str) -> List[str]:
        """Extract all annotations as a list of strings."""
        return [match.group(1).strip() for match in self.ANNOTATION_PATTERN.finditer(script)]

    def get_full_narration(self, parsed: ParsedScript) -> str:
        """Get the complete narration text from parsed segments."""
        return " ".join(seg.text for seg in parsed.narration_segments)

    def get_scene_descriptions(self, parsed: ParsedScript) -> List[dict]:
        """
        Convert parsed script into scene descriptions for video generation.

        Returns a list of dicts with narration and visual cue for each scene.
        """
        scenes = []

        for i, cue in enumerate(parsed.visual_cues):
            scene = {
                "scene_number": i + 1,
                "visual_description": cue.annotation,
                "narration_before": cue.preceding_narration,
            }

            next_cue_index = i + 1
            if next_cue_index < len(parsed.visual_cues):
                next_cue_start = parsed.visual_cues[next_cue_index].start_index
                for seg in parsed.narration_segments:
                    if cue.end_index <= seg.start_index < next_cue_start:
                        scene["narration_after"] = seg.text
                        break
            else:
                for seg in parsed.narration_segments:
                    if seg.start_index >= cue.end_index:
                        scene["narration_after"] = seg.text
                        break

            scenes.append(scene)

        return scenes


def parse_script(script: str) -> ParsedScript:
    """Convenience function to parse a script."""
    parser = ScriptParser()
    return parser.parse(script)
