"""Normalize provider-specific model metadata into standard model_configs fields."""

from typing import Any


def normalize_provider_model(provider_type: str, model_data: dict[str, Any]) -> dict[str, Any]:
    if provider_type == "atlascloud":
        return _normalize_atlascloud(model_data)
    elif provider_type == "poe":
        return _normalize_poe(model_data)
    raise ValueError(f"Unknown provider type: {provider_type}")


def _normalize_atlascloud(m: dict[str, Any]) -> dict[str, Any]:
    atype = m.get("type", "Text").lower()
    model_id = m.get("model", "").lower()
    caps = {"supports_chat": atype == "text"}
    
    # Parse model ID for task-type: {provider}/{family}/{task-type}
    # Task-types: text-to-image, image-to-image, edit, text-to-video, image-to-video, etc.
    if atype == "image":
        if any(x in model_id for x in ("/edit", "image-edit", "image-to-image", "img2img")):
            caps.update({"accepts_image": True, "accepts_text": True, "outputs_image": True})
        else:
            caps.update({"accepts_text": True, "outputs_image": True})
    elif atype == "video":
        if "image-to-video" in model_id or "/i2v" in model_id:
            caps.update({"accepts_image": True, "outputs_video": True})
        elif "reference-to-video" in model_id:
            caps.update({"accepts_image": True, "accepts_video": True, "outputs_video": True})
        elif any(x in model_id for x in ("extend-video", "video-edit", "video-to-video", "/v2v")):
            caps.update({"accepts_video": True, "outputs_video": True})
        elif "text-to-video" in model_id or "/t2v" in model_id:
            caps.update({"accepts_text": True, "outputs_video": True})
        else:
            caps.update({"accepts_text": True, "outputs_video": True})
    elif atype == "text":
        caps.update({"accepts_text": True, "outputs_text": True})
    return {
        "model_id": m["model"],
        "provider_model_id": m["model"],
        "display_name": m.get("displayName") or m["model"],
        "modality": atype,
        "endpoint_type": (
            "generateImage" if atype == "image" else
            "generateVideo" if atype == "video" else
            "chat_completions"
        ),
        "capabilities": caps,
        "cost_config": {"currency": "credits"},
    }


def _normalize_poe(m: dict[str, Any]) -> dict[str, Any]:
    arch = m.get("architecture", {})
    inputs = set(arch.get("input_modalities", []))
    outputs = set(arch.get("output_modalities", []))
    features = set(m.get("supported_features", []))
    endpoints = set(m.get("supported_endpoints", []))
    pricing = m.get("pricing") or {}
    ctx = m.get("context_window") or {}

    if "video" in outputs:
        modality = "video"
    elif "image" in outputs:
        modality = "image"
    else:
        modality = "text"

    if "/v1/images" in endpoints or modality == "image":
        endpoint = "generateImage"
    elif modality == "video":
        endpoint = "generateVideo"
    else:
        endpoint = "chat_completions"

    caps: dict[str, Any] = {
        "accepts_text": "text" in inputs,
        "accepts_image": "image" in inputs,
        "accepts_video": "video" in inputs,
        "outputs_text": "text" in outputs,
        "outputs_image": "image" in outputs,
        "outputs_video": "video" in outputs,
        "supports_tools": "tools" in features,
        "supports_web_search": "web_search" in features,
    }

    result: dict[str, Any] = {
        "model_id": m["id"],
        "provider_model_id": m.get("root") or m["id"],
        "display_name": (m.get("metadata", {}).get("display_name") or m.get("id", "")),
        "modality": modality,
        "endpoint_type": endpoint,
        "capabilities": caps,
    }

    if ctx and (ctx.get("context_length") or ctx.get("max_output_tokens")):
        result["constraints"] = {
            "context_length": ctx.get("context_length"),
            "max_output_tokens": ctx.get("max_output_tokens"),
        }

    if pricing:
        cost = {"currency": pricing.get("currency", "compute_points")}
        cp = pricing.get("compute_points")
        if cp is not None:
            cost["compute_points"] = cp
        result["cost_config"] = cost

    return result
