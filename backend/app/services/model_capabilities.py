"""Model capability types and normalization utilities.

Provides structured enums and a Pydantic model for representing what a model
can do (text-to-image, image-to-video, etc.) and a normalizer that infers
these from the loose ``accepts_*`` / ``outputs_*`` boolean dict stored in the
database.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

# ── Enums ──────────────────────────────────────────────────────────────────


class ModelCapability(str, Enum):
    """Granular capability flags that a model can advertise."""

    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_EDIT = "image_edit"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    FRAME_TO_VIDEO = "frame_to_video"
    MULTI_REF_TO_VIDEO = "multi_ref_to_video"
    TEXT_TO_TEXT = "text_to_text"
    UNKNOWN = "unknown"


class GenerationType(str, Enum):
    """Primary generation mode of a model.

    This is the single *most specific* mode inferred from the model's
    capability flags.
    """

    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_EDIT = "image_edit"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    FRAME_TO_VIDEO = "frame_to_video"
    MULTI_REF_TO_VIDEO = "multi_ref_to_video"
    UNKNOWN = "unknown"


# ── Structured model ───────────────────────────────────────────────────────


class ModelCapabilities(BaseModel):
    """Normalised representation of a model's capability flags.

    All fields are derived from the loose JSONB dict stored in
    ``ModelConfig.capabilities``.
    """

    accepts_text: bool = False
    accepts_image: bool = False
    accepts_start_end_images: bool = False
    accepts_multiple_images: bool = False
    accepts_video: bool = False
    outputs_image: bool = False
    outputs_video: bool = False
    outputs_text: bool = False
    generation_type: GenerationType = GenerationType.UNKNOWN
    capabilities: list[ModelCapability] = []


# ── Normalizer ─────────────────────────────────────────────────────────────


def normalize_capabilities(raw: dict) -> ModelCapabilities:
    """Convert a loose capability dict to a structured ``ModelCapabilities``.

    The *raw* dict is what provider ``list_models`` implementations produce
    (keys like ``accepts_text``, ``outputs_video``, …).  This function infers
    the ``generation_type`` and populates the ``capabilities`` list so that
    downstream code can reason about models in a type-safe way.

    Parameters
    ----------
    raw : dict
        Capability flags, typically deserialised from the JSONB column.

    Returns
    -------
    ModelCapabilities
        A validated, normalised capabilities object.
    """
    at = raw.get("accepts_text", False)
    ai = raw.get("accepts_image", False)
    asi = raw.get("accepts_start_end_images", False)
    ami = raw.get("accepts_multiple_images", False)
    av = raw.get("accepts_video", False)
    oi = raw.get("outputs_image", False)
    ov = raw.get("outputs_video", False)
    ot = raw.get("outputs_text", False)

    caps: set[ModelCapability] = set()

    if ot:
        caps.add(ModelCapability.TEXT_TO_TEXT)

    if oi:
        if ai:
            caps.add(ModelCapability.IMAGE_TO_IMAGE)
            caps.add(ModelCapability.IMAGE_EDIT)
        if at:
            caps.add(ModelCapability.TEXT_TO_IMAGE)
        if not ai and not at:
            caps.add(ModelCapability.TEXT_TO_IMAGE)

    if ov:
        if asi:
            caps.add(ModelCapability.FRAME_TO_VIDEO)
        if ami:
            caps.add(ModelCapability.MULTI_REF_TO_VIDEO)
        if ai:
            caps.add(ModelCapability.IMAGE_TO_VIDEO)
        if at or not (ai or asi or ami or av):
            caps.add(ModelCapability.TEXT_TO_VIDEO)

    if ai and not (oi or ov or ot):
        caps.add(ModelCapability.IMAGE_TO_IMAGE)

    if not caps:
        caps.add(ModelCapability.UNKNOWN)

    # Determine generation type (most specific wins)
    gen_type = _infer_generation_type(at, ai, asi, ami, av, oi, ov, ot)

    return ModelCapabilities(
        accepts_text=at,
        accepts_image=ai,
        accepts_start_end_images=asi,
        accepts_multiple_images=ami,
        accepts_video=av,
        outputs_image=oi,
        outputs_video=ov,
        outputs_text=ot,
        generation_type=gen_type,
        capabilities=sorted(caps, key=lambda c: c.value),
    )


def _infer_generation_type(
    at: bool,
    ai: bool,
    asi: bool,
    ami: bool,
    av: bool,
    oi: bool,
    ov: bool,
    ot: bool,
) -> GenerationType:
    """Internal helper — pick the most specific generation type."""
    if ov:
        if asi:
            return GenerationType.FRAME_TO_VIDEO
        if ami:
            return GenerationType.MULTI_REF_TO_VIDEO
        if ai:
            return GenerationType.IMAGE_TO_VIDEO
        if at:
            return GenerationType.TEXT_TO_VIDEO
    if oi:
        if ai:
            return GenerationType.IMAGE_TO_IMAGE
        if at:
            return GenerationType.TEXT_TO_IMAGE
    if ot:
        return GenerationType.UNKNOWN
    return GenerationType.UNKNOWN


# ── Scene planner context builder ──────────────────────────────────────────

_GENERATION_TYPE_INSTRUCTIONS: dict[GenerationType, str] = {
    GenerationType.TEXT_TO_IMAGE: "text prompt only — no reference image needed",
    GenerationType.IMAGE_TO_IMAGE: "text prompt + 1 reference image",
    GenerationType.IMAGE_EDIT: "text prompt + 1 reference image (edit mode)",
    GenerationType.TEXT_TO_VIDEO: "text prompt only → video",
    GenerationType.IMAGE_TO_VIDEO: "text prompt + 1 reference image → video",
    GenerationType.FRAME_TO_VIDEO: "text prompt + start image + end image → video",
    GenerationType.MULTI_REF_TO_VIDEO: "text prompt + multiple reference images → video",
    GenerationType.UNKNOWN: "unknown capability",
}

_SCENE_INSTRUCTIONS: dict[GenerationType, str] = {
    GenerationType.TEXT_TO_IMAGE: (
        "For each scene: describe the desired image in detail. "
        "No reference image is needed."
    ),
    GenerationType.IMAGE_TO_IMAGE: (
        "For each scene: use a reference image combined with a "
        "descriptive text prompt."
    ),
    GenerationType.IMAGE_EDIT: (
        "For each scene: provide a base image and edit instructions."
    ),
    GenerationType.TEXT_TO_VIDEO: (
        "For each scene: describe the desired video clip in detail. "
        "No reference image is available."
    ),
    GenerationType.IMAGE_TO_VIDEO: (
        "For each scene: provide ONE seed image that serves as the "
        "first frame of the video clip."
    ),
    GenerationType.FRAME_TO_VIDEO: (
        "For each scene: provide start and end frame reference images "
        "for video transition."
    ),
    GenerationType.MULTI_REF_TO_VIDEO: (
        "For each scene: provide multiple reference images to guide "
        "video generation."
    ),
}


def build_model_capabilities_context(
    video_model_config: dict | None = None,
    image_model_config: dict | None = None,
) -> str:
    """Generate a structured ``MODEL CAPABILITIES`` block for scene-planner prompts.

    Reads the capabilities and constraints from the model-config dicts (as
    returned by :func:`~app.api.models._model_config_to_dict`) and produces a
    human-readable description that tells the LLM planner exactly what each
    model can do, what inputs it requires, and what limits apply.

    Parameters
    ----------
    video_model_config : dict | None
        Dict with keys ``display_name``, ``capabilities``, ``constraints``,
        ``max_duration``, etc.  ``None`` means no video model is selected.
    image_model_config : dict | None
        Same shape for the image model.

    Returns
    -------
    str
        Multi-line text block suitable for injection into a planner system prompt.
    """
    lines: list[str] = []

    # ── Video model section ──
    lines.append("VIDEO MODEL CAPABILITIES:")
    if video_model_config:
        lines.extend(
            _build_model_section(video_model_config, modality="video")
        )
    else:
        lines.append("  No video model selected.")

    lines.append("")

    # ── Image model section ──
    lines.append("IMAGE MODEL CAPABILITIES:")
    if image_model_config:
        lines.extend(
            _build_model_section(image_model_config, modality="image")
        )
    else:
        lines.append("  No image model selected.")

    return "\n".join(lines)


def _build_model_section(config: dict, *, modality: str) -> list[str]:
    """Build the indented description lines for a single model."""
    lines: list[str] = []

    # Model name
    name = (
        config.get("display_name")
        or config.get("name")
        or config.get("id")
        or "unknown"
    )
    lines.append(f"  Model: {name}")

    # Capabilities
    caps_raw = config.get("capabilities", {})
    if isinstance(caps_raw, dict):
        caps = normalize_capabilities(caps_raw)
    elif isinstance(caps_raw, list):
        # Back-compat: capabilities stored as a list of strings.
        # Fall back to a vanilla ModelCapabilities (all defaults).
        caps = ModelCapabilities()
    else:
        caps = ModelCapabilities()

    gen_type = caps.generation_type
    instruction = _GENERATION_TYPE_INSTRUCTIONS.get(
        gen_type, "unknown capability"
    )
    lines.append(f"  Generation type: {gen_type.value} ({instruction})")

    # ── Constraints ──
    constraints: dict = config.get("constraints") or {}

    if modality == "video":
        max_dur = config.get("max_duration") or constraints.get("max_duration")
        if max_dur is not None:
            lines.append(f"  Max clip duration: {max_dur} seconds")

    if modality == "image":
        # Resolutions (could be under 'resolutions' or 'constraints.resolutions')
        resolutions = config.get("resolutions") or constraints.get("resolutions")
        if resolutions and isinstance(resolutions, list):
            lines.append(
                f"  Supported resolutions: {', '.join(str(r) for r in resolutions)}"
            )

        max_res = config.get("max_resolution") or constraints.get("max_resolution")
        if max_res:
            lines.append(f"  Max resolution: {max_res}")

    # ── Per-scene guidance ──
    scene_instruction = _SCENE_INSTRUCTIONS.get(gen_type)
    if scene_instruction:
        lines.append(f"  {scene_instruction}")

    return lines


__all__ = [
    "GenerationType",
    "ModelCapabilities",
    "ModelCapability",
    "build_model_capabilities_context",
    "normalize_capabilities",
]
