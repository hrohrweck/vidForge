import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.config import get_settings
from app.services import ComfyUIClient
from app.services.audio_generation import (
    MusicGenService,
    TTSService,
    generate_background_music,
    generate_narration,
)
from app.services.llm_service import enhance_prompt_for_video, segment_script_for_video
from app.services.template_loader import (
    TemplateLoader,
    StyleLoader,
    load_comfyui_workflow,
    merge_style_into_workflow,
)
from app.services.video_processor import VideoProcessor

settings = get_settings()


class VideoGenerationError(Exception):
    pass


class VideoGenerator:
    def __init__(self, job_id: str, output_dir: Path):
        self.job_id = job_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.comfyui = ComfyUIClient()
        self.template_loader = TemplateLoader(settings.templates_path)
        self.style_loader = StyleLoader(settings.styles_path)

    async def close(self):
        await self.comfyui.close()

    async def generate(
        self,
        template_name: str,
        input_data: dict[str, Any],
        style_name: str | None = None,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> tuple[str, str | None]:
        template = self.template_loader.load_template(template_name)

        style_params = {}
        if style_name:
            style = self.style_loader.load_style(style_name)
            style_params = style.get("params", {})

        if progress_callback:
            await progress_callback(5, "Loading template")

        context = {"job_id": self.job_id, "output_dir": str(self.output_dir)}
        context.update(input_data)

        final_video = None
        preview_video = None

        for i, step in enumerate(template.get("pipeline", [])):
            step_name = step.get("step")
            condition = step.get("condition")

            if condition and not self._evaluate_condition(condition, context):
                continue

            if progress_callback:
                progress = 10 + (i * 60 // len(template.get("pipeline", [])))
                await progress_callback(progress, f"Processing: {step_name}")

            if step_name == "enhance_prompt":
                result = await self._enhance_prompt(step, context)
                context.update(result)
            elif step_name == "segment_script":
                result = await self._segment_script(step, context)
                context.update(result)
            elif step_name == "generate_segments":
                result = await self._generate_segments(step, context, style_params)
                context.update(result)
                final_video = result.get("merged_video")
            elif step_name == "generate_video":
                result = await self._generate_video(step, context, style_params)
                context.update(result)
                final_video = result.get("video")
            elif step_name == "generate_narration":
                result = await self._generate_narration(step, context)
                context.update(result)
            elif step_name == "generate_audio":
                result = await self._generate_audio(step, context)
                context.update(result)
            elif step_name == "combine":
                result = await self._combine_av(step, context)
                context.update(result)
                final_video = result.get("final_video", final_video)
            elif step_name == "generate_preview":
                if final_video:
                    preview_video = await self._generate_preview(final_video)
                    context["preview"] = preview_video

        if progress_callback:
            await progress_callback(95, "Finalizing")

        if not final_video:
            raise VideoGenerationError("No video was generated")

        return final_video, preview_video

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return False

    async def _enhance_prompt(self, step: dict, context: dict) -> dict[str, Any]:
        prompt = context.get("prompt", "")
        style = context.get("style", "realistic")

        use_llm = step.get("params", {}).get("use_llm", True)

        if use_llm:
            try:
                enhanced = await enhance_prompt_for_video(prompt, style, context)
            except Exception:
                style_prompts = {
                    "realistic": "photorealistic, detailed, high quality, cinematic",
                    "anime": "anime style, vibrant colors, detailed animation",
                    "manga": "manga style, black and white, dramatic shading",
                }
                style_suffix = style_prompts.get(style, "")
                enhanced = f"{prompt}, {style_suffix}" if style_suffix else prompt
        else:
            style_prompts = {
                "realistic": "photorealistic, detailed, high quality, cinematic",
                "anime": "anime style, vibrant colors, detailed animation",
                "manga": "manga style, black and white, dramatic shading",
            }
            style_suffix = style_prompts.get(style, "")
            enhanced = f"{prompt}, {style_suffix}" if style_suffix else prompt

        return {"enhanced_prompt": enhanced}

    async def _segment_script(self, step: dict, context: dict) -> dict[str, Any]:
        script = context.get("script", context.get("prompt", ""))
        style = context.get("style", "realistic")
        total_duration = context.get("duration", 30)

        use_llm = step.get("params", {}).get("use_llm", True)

        if use_llm:
            try:
                segments = await segment_script_for_video(script, style, total_duration)
            except Exception:
                segments = self._fallback_segment_script(script, total_duration)
        else:
            segments = self._fallback_segment_script(script, total_duration)

        return {"segments": segments, "segment_count": len(segments)}

    def _fallback_segment_script(self, script: str, total_duration: float) -> list[dict[str, Any]]:
        import re

        annotations = re.findall(r"\[([^\]]+)\]", script)
        clean_script = re.sub(r"\[[^\]]+\]", "", script).strip()
        sentences = re.split(r"[.!?]+", clean_script)
        sentences = [s.strip() for s in sentences if s.strip()]

        if annotations:
            num_segments = len(annotations)
        else:
            num_segments = max(1, min(len(sentences), int(total_duration / 3)))

        segment_duration = total_duration / num_segments
        segments = []

        for i in range(num_segments):
            if i < len(annotations):
                visual = annotations[i]
            elif i < len(sentences):
                visual = f"Visual representation of: {sentences[i]}"
            else:
                visual = "Abstract visual sequence"

            narration = sentences[i] if i < len(sentences) else ""

            segments.append(
                {
                    "duration": segment_duration,
                    "visual": visual,
                    "narration": narration,
                }
            )

        return segments

    async def _generate_segments(
        self, step: dict, context: dict, style_params: dict
    ) -> dict[str, Any]:
        segments = context.get("segments", [])
        if not segments:
            return {"segment_videos": [], "merged_video": None}

        segment_videos = []
        fps = context.get("fps", 24)
        aspect_ratio = context.get("aspect_ratio", "16:9")
        width, height = self._get_dimensions(aspect_ratio)

        segments_dir = self.output_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)

        for i, segment in enumerate(segments):
            segment_duration = segment.get("duration", 3)
            segment_prompt = segment.get("visual", "")

            workflow_path = Path(settings.comfyui_workflows_path) / "wan_t2v.json"
            workflow = load_comfyui_workflow(str(workflow_path))
            workflow = merge_style_into_workflow(workflow, style_params)

            video_length = int(segment_duration * fps) + 1

            for node_id, node in workflow.items():
                if node.get("class_type") == "WanVideoSampler":
                    node["inputs"]["prompt"] = segment_prompt
                    node["inputs"]["width"] = width
                    node["inputs"]["height"] = height
                    node["inputs"]["video_length"] = video_length
                    node["inputs"]["fps"] = fps
                elif node.get("class_type") == "SaveVideo":
                    node["inputs"]["filename_prefix"] = f"segment_{i:03d}"

            result = await self.comfyui.queue_prompt(workflow)
            prompt_id = result.get("prompt_id")

            if not prompt_id:
                continue

            history = await self.comfyui.wait_for_completion(prompt_id, timeout=600)

            output_filename = None
            for node_output in history.get("outputs", {}).values():
                if "videos" in node_output:
                    videos = node_output["videos"]
                    if videos:
                        output_filename = videos[0].get("filename")
                        break

            if output_filename:
                video_data = await self.comfyui.get_output(output_filename, subfolder="output")
                segment_path = segments_dir / f"segment_{i:03d}.mp4"
                segment_path.write_bytes(video_data)
                segment_videos.append(str(segment_path))

        if len(segment_videos) == 0:
            return {"segment_videos": [], "merged_video": None}

        if len(segment_videos) == 1:
            return {"segment_videos": segment_videos, "merged_video": segment_videos[0]}

        merged_path = self.output_dir / "merged.mp4"
        await VideoProcessor.merge_videos(segment_videos, str(merged_path))

        return {"segment_videos": segment_videos, "merged_video": str(merged_path)}

    async def _generate_video(
        self, step: dict, context: dict, style_params: dict
    ) -> dict[str, Any]:
        workflow_name = step.get("model", "wan_t2v")
        workflow_path = Path(settings.comfyui_workflows_path) / f"{workflow_name}.json"

        if not workflow_path.exists():
            workflow_path = Path(settings.comfyui_workflows_path) / "wan_t2v.json"

        workflow = load_comfyui_workflow(str(workflow_path))
        workflow = merge_style_into_workflow(workflow, style_params)

        prompt = context.get("enhanced_prompt", context.get("prompt", ""))
        duration = context.get("duration", 5)
        fps = context.get("fps", 24)
        aspect_ratio = context.get("aspect_ratio", "16:9")

        width, height = self._get_dimensions(aspect_ratio)
        video_length = int(duration * fps) + 1

        for node_id, node in workflow.items():
            if node.get("class_type") == "WanVideoSampler":
                node["inputs"]["prompt"] = prompt
                node["inputs"]["width"] = width
                node["inputs"]["height"] = height
                node["inputs"]["video_length"] = video_length
                node["inputs"]["fps"] = fps
            elif node.get("class_type") == "SaveVideo":
                node["inputs"]["filename_prefix"] = f"job_{self.job_id}"

        result = await self.comfyui.queue_prompt(workflow)
        prompt_id = result.get("prompt_id")

        if not prompt_id:
            raise VideoGenerationError("Failed to queue ComfyUI prompt")

        history = await self.comfyui.wait_for_completion(prompt_id, timeout=1800)

        output_filename = None
        for node_output in history.get("outputs", {}).values():
            if "videos" in node_output:
                videos = node_output["videos"]
                if videos:
                    output_filename = videos[0].get("filename")
                    break

        if not output_filename:
            raise VideoGenerationError("No video output from ComfyUI")

        video_data = await self.comfyui.get_output(output_filename, subfolder="output")
        video_path = self.output_dir / "video.mp4"
        video_path.write_bytes(video_data)

        return {"video": str(video_path)}

    async def _generate_audio(self, step: dict, context: dict) -> dict[str, Any]:
        prompt = context.get("prompt", "")
        duration = context.get("duration", 5)
        audio_type = step.get("params", {}).get("type", "music")

        audio_path = self.output_dir / "audio.mp3"

        try:
            if audio_type == "narration":
                script = context.get("script", prompt)
                voice = step.get("params", {}).get("voice", "en-US-AriaNeural")
                tts_backend = step.get("params", {}).get("tts_backend", "edge")

                tts = TTSService(self.output_dir)
                await tts.generate(
                    text=script,
                    output_path=str(audio_path),
                    voice=voice,
                    backend=tts_backend,
                )

                if audio_path.exists():
                    return {"audio": str(audio_path)}

            elif audio_type == "music":
                music_service = MusicGenService(self.output_dir)
                await music_service.generate(
                    prompt=prompt,
                    output_path=str(audio_path).replace(".mp3", ".wav"),
                    duration=duration,
                    model=step.get("params", {}).get("model", "facebook/musicgen-small"),
                )

                wav_path = Path(str(audio_path).replace(".mp3", ".wav"))
                if wav_path.exists():
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg",
                        "-i",
                        str(wav_path),
                        "-y",
                        str(audio_path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                    wav_path.unlink()

                    if audio_path.exists():
                        return {"audio": str(audio_path)}

            else:
                proc = await asyncio.create_subprocess_exec(
                    "python",
                    "-m",
                    "audiocraft",
                    "generate",
                    "--prompt",
                    prompt,
                    "--duration",
                    str(duration),
                    "--output",
                    str(audio_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                if audio_path.exists():
                    return {"audio": str(audio_path)}
        except Exception:
            pass

        return {"audio": None}

    async def _generate_narration(self, step: dict, context: dict) -> dict[str, Any]:
        script = context.get("script", context.get("prompt", ""))
        voice = step.get("params", {}).get("voice", "en-US-AriaNeural")
        tts_backend = step.get("params", {}).get("backend", "edge")

        narration_path = self.output_dir / "narration.mp3"

        try:
            tts = TTSService(self.output_dir)
            await tts.generate(
                text=script,
                output_path=str(narration_path),
                voice=voice,
                backend=tts_backend,
            )

            if narration_path.exists():
                duration = await self._get_audio_duration(str(narration_path))
                return {
                    "audio": str(narration_path),
                    "narration_duration": duration,
                }
        except Exception:
            pass

        return {"audio": None, "narration_duration": 0}

    async def _get_audio_duration(self, audio_path: str) -> float:
        import json

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout.decode())
        return float(info.get("format", {}).get("duration", 0))

    async def _combine_av(self, step: dict, context: dict) -> dict[str, Any]:
        video_path = context.get("video")
        audio_path = context.get("audio")

        if not video_path or not audio_path:
            return {"final_video": video_path}

        output_path = self.output_dir / "final.mp4"
        await VideoProcessor.add_audio(video_path, audio_path, str(output_path))

        return {"final_video": str(output_path)}

    async def _generate_preview(self, video_path: str) -> str:
        preview_path = self.output_dir / "preview.mp4"
        await VideoProcessor.generate_preview(
            video_path,
            str(preview_path),
            width=854,
            height=480,
            fps=15,
        )
        return str(preview_path)

    def _get_dimensions(self, aspect_ratio: str) -> tuple[int, int]:
        base_width = 1280
        ratios = {
            "16:9": (base_width, int(base_width * 9 / 16)),
            "9:16": (int(base_width * 9 / 16), base_width),
            "1:1": (base_width, base_width),
        }
        return ratios.get(aspect_ratio, ratios["16:9"])


async def process_job_video(
    job_id: str,
    template_name: str,
    input_data: dict[str, Any],
    progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
) -> tuple[str, str | None]:
    output_dir = Path(settings.storage_path) / "output" / job_id
    generator = VideoGenerator(job_id, output_dir)

    try:
        style_name = input_data.get("style", "realistic")
        return await generator.generate(template_name, input_data, style_name, progress_callback)
    finally:
        await generator.close()
