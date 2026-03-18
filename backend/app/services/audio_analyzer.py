import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any


class AudioAnalyzer:
    """Analyze audio files for video generation."""

    @staticmethod
    async def get_duration(audio_path: str) -> float:
        """Get audio duration in seconds."""
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

    @staticmethod
    async def get_audio_info(audio_path: str) -> dict:
        """Get comprehensive audio metadata."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return json.loads(stdout.decode())

    @staticmethod
    async def analyze_beats(audio_path: str) -> list[float]:
        """Detect beats in audio file using librosa if available."""
        try:
            import numpy as np

            try:
                import librosa
            except ImportError:
                return await AudioAnalyzer._ffmpeg_beat_detection(audio_path)

            y, sr = librosa.load(audio_path, sr=None)

            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)

            return beat_times.tolist()

        except ImportError:
            return await AudioAnalyzer._ffmpeg_beat_detection(audio_path)
        except Exception:
            return await AudioAnalyzer._ffmpeg_beat_detection(audio_path)

    @staticmethod
    async def _ffmpeg_beat_detection(audio_path: str) -> list[float]:
        """Fallback beat detection using ffmpeg silencedetect."""
        try:
            cmd = [
                "ffmpeg",
                "-i",
                audio_path,
                "-af",
                "silencedetect=noise=-30dB:d=0.1",
                "-f",
                "null",
                "-",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            beats = []
            output = stderr.decode()

            for line in output.split("\n"):
                if "silence_end:" in line:
                    try:
                        time_str = line.split("silence_end:")[1].split()[0]
                        beats.append(float(time_str))
                    except (IndexError, ValueError):
                        continue

            if len(beats) < 2:
                return await AudioAnalyzer._uniform_beats(audio_path)

            return beats

        except Exception:
            return await AudioAnalyzer._uniform_beats(audio_path)

    @staticmethod
    async def _uniform_beats(audio_path: str) -> list[float]:
        """Generate uniform beat times based on estimated BPM."""
        duration = await AudioAnalyzer.get_duration(audio_path)

        estimated_bpm = 120
        beat_interval = 60.0 / estimated_bpm

        beats = []
        t = 0.0
        while t < duration:
            beats.append(t)
            t += beat_interval

        return beats

    @staticmethod
    async def estimate_mood(audio_path: str) -> str:
        """Estimate mood/tempo of audio."""
        try:
            import librosa

            y, sr = librosa.load(audio_path, sr=None)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

            if isinstance(tempo, np.ndarray):
                tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
            else:
                tempo = float(tempo)

            if tempo > 140:
                return "energetic"
            elif tempo > 100:
                return "upbeat"
            elif tempo > 70:
                return "moderate"
            else:
                return "calm"

        except ImportError:
            pass
        except Exception:
            pass

        info = await AudioAnalyzer.get_audio_info(audio_path)
        duration = float(info.get("format", {}).get("duration", 0))

        if duration < 30:
            return "energetic"
        elif duration < 120:
            return "moderate"
        else:
            return "calm"

    @staticmethod
    async def get_tempo(audio_path: str) -> float:
        """Get estimated tempo in BPM."""
        try:
            import librosa

            y, sr = librosa.load(audio_path, sr=None)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

            if isinstance(tempo, np.ndarray):
                return float(tempo[0]) if len(tempo) > 0 else 120.0
            return float(tempo)

        except ImportError:
            pass
        except Exception:
            pass

        return 120.0

    @staticmethod
    async def analyze_for_video(audio_path: str, target_fps: int = 24) -> dict[str, Any]:
        """Comprehensive analysis for video synchronization."""
        duration = await AudioAnalyzer.get_duration(audio_path)
        beats = await AudioAnalyzer.analyze_beats(audio_path)
        mood = await AudioAnalyzer.estimate_mood(audio_path)
        tempo = await AudioAnalyzer.get_tempo(audio_path)

        beat_intervals = []
        for i in range(1, len(beats)):
            beat_intervals.append(beats[i] - beats[i - 1])

        avg_beat_interval = sum(beat_intervals) / len(beat_intervals) if beat_intervals else 0.5

        transition_frames = []
        for beat_time in beats:
            frame = int(beat_time * target_fps)
            transition_frames.append(frame)

        suggested_cuts = AudioAnalyzer._suggest_cut_points(beats, duration)

        return {
            "duration": duration,
            "beats": beats,
            "beat_count": len(beats),
            "mood": mood,
            "tempo": tempo,
            "avg_beat_interval": avg_beat_interval,
            "transition_frames": transition_frames,
            "suggested_cuts": suggested_cuts,
            "target_fps": target_fps,
        }

    @staticmethod
    def _suggest_cut_points(beats: list[float], duration: float) -> list[dict[str, Any]]:
        """Suggest video cut points based on beats."""
        if len(beats) < 2:
            return [{"time": 0.0, "type": "start"}, {"time": duration, "type": "end"}]

        cuts = [{"time": 0.0, "type": "start"}]

        num_segments = min(len(beats) // 4, 10)
        if num_segments < 2:
            num_segments = 2

        segment_duration = duration / num_segments

        for i in range(1, num_segments):
            target_time = i * segment_duration

            closest_beat = min(beats, key=lambda b: abs(b - target_time))
            if abs(closest_beat - target_time) < segment_duration * 0.3:
                cuts.append({"time": closest_beat, "type": "beat_cut"})
            else:
                cuts.append({"time": target_time, "type": "time_cut"})

        cuts.append({"time": duration, "type": "end"})

        return cuts


try:
    import numpy as np
except ImportError:
    np = None
