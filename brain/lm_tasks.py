"""Task/provider policy for the existing LM gateway.

These are preferences, not proof of capability or production activation. A pair
must be independently registered and tested before the gateway may execute it.
Raw model IDs below were read from the Gateway's registered endpoint models.
"""
from __future__ import annotations

PROVIDERS = {
    "google": {"title": "Google AI Studio", "group": None, "prefix": "google:", "quota": None},
    "jarvis": {"title": "Jarvis", "group": "jarvis-all-models", "quota": None},
    "arvancloud": {"title": "ArvanCloud", "group": "arvancloud-all-models", "quota": None},
    "sarovi": {"title": "Sarovi", "group": "sarovi-all-models", "quota": None},
    "openai": {"title": "OpenAI", "group": "openai-all-models", "quota": None},
}


def qualified_id(provider: str, model_id: str) -> str:
    """Only approved groups; preserve case, punctuation and slashes verbatim."""
    item = PROVIDERS[provider]
    if not model_id or len(model_id) > 400 or "#" in model_id or any(c.isspace() for c in model_id):
        raise ValueError("Invalid registered model ID")
    if model_id.startswith(("custom:", "google:")):
        raise ValueError("Expected the raw registered model ID")
    return f"custom:{model_id}#{item['group']}" if item["group"] else item["prefix"] + model_id


# Operator priority: Jarvis first, then Sarovi, then ArvanCloud, then OpenAI. Gemini/Google models are the one exception:
# Google itself is asked first for those. Anything unrecognised (``auto``, legacy ids) goes last.
PRIORITY = ("jarvis", "sarovi", "arvancloud", "openai")


def provider_of(model_id: str) -> str:
    """Provider of a registered model id (``custom:<raw>#<group>`` / ``google:<raw>``); ``""`` when it cannot be told."""
    if model_id.startswith("google:"):
        return "google"
    if model_id.startswith("custom:") and "#" in model_id:
        group = model_id.rsplit("#", 1)[1]
        for name, item in PROVIDERS.items():
            if item.get("group") == group:
                return name
    return ""


def rank(model_id: str) -> int:
    provider = provider_of(model_id)
    if provider == "google":
        return -1
    return PRIORITY.index(provider) if provider in PRIORITY else len(PRIORITY)


def prioritize(model_ids: list[str]) -> list[str]:
    """Stable reorder by the operator priority; models of the same provider keep the order the operator gave them."""
    return [mid for _, mid in sorted(enumerate(model_ids), key=lambda pair: (rank(pair[1]), pair[0]))]


def ordered(pairs):
    """Same ordering for ``(provider, model_id)`` pairs (used by the policy below)."""
    def key(item):
        provider = item[1][0]
        return (-1 if provider == "google" else PRIORITY.index(provider) if provider in PRIORITY else len(PRIORITY), item[0])
    return [pair for _, pair in sorted(enumerate(pairs), key=key)]


# Cross-provider versions may differ; never pretend Opus 5.5 exists on Arvan.
POWER = ordered([("jarvis", "CLAUDE_OPUS_5_5"), ("arvancloud", "Claude-Opus-4.7")])
STORY = ordered([("jarvis", "CLAUDE_SONNET_5_5"), ("arvancloud", "Claude-Sonnet-4.6")])
LIGHT = ordered([("google", "gemini-3.5-flash"), ("arvancloud", "DeepSeek-V4-Flash"),
                 ("arvancloud", "GLM-5.3-Flash"), ("jarvis", "DEEPSEEK_V4_FLASH")])
VISION = ordered([("jarvis", "GPT_5_6_SOL"), ("google", "gemini-3.1-pro-preview"),
                  ("arvancloud", "GPT-5.6-Sol")])


def _task(title, capability, pairs, parent):
    return {"title": title, "capability": capability, "parent": parent,
            "preferences": [{"provider": p, "model_id": m, "id": qualified_id(p, m)} for p,m in pairs]}


TASKS = {
    "conversation_response": _task("Conversation · Immediate Response", "chat", LIGHT, "general_chat"),
    "intent_classification": _task("Intent Classification", "chat", LIGHT, "editing_agent"),
    "general_chat": _task("General Chat", "chat", LIGHT, "general_chat"),
    "edit_planning": _task("Edit Planning", "chat", POWER, "editing_agent"),
    "hyperframes_design": _task("HyperFrames Design", "chat", POWER, "editing_agent"),
    "remotion_design": _task("Remotion Design", "chat", POWER, "editing_agent"),
    "complex_editing_agent": _task("Complex Editing Agent", "chat", POWER, "editing_agent"),
    "storyboard_generation": _task("Storyboard Generation", "chat", STORY, "editing_agent"),
    "video_understanding": _task("Video Understanding", "vision", VISION, "video_understanding"),
    "effects_v4_vision": _task("Effects V4 Vision", "vision", VISION, "video_understanding"),
    "visual_qc": _task("Visual QC", "vision", VISION, "video_understanding"),
    # Creative Engine (creative/): concept exploration and critique need the strongest models; revision parsing is lighter.
    "creative_director": _task("Creative Director", "chat", POWER, "editing_agent"),
    "creative_critic": _task("Creative Critic", "chat", POWER, "editing_agent"),
    "creative_revision": _task("Creative Revision", "chat", STORY, "editing_agent"),
    "creative_motion": _task("Creative Motion Designer", "chat", POWER, "editing_agent"),
    # Hermes (Instagram agent): Jarvis first with the strongest Claude, then Sonnet 5.5 on Jarvis, then ArvanCloud's Claude (the operator order Jarvis > Arvan);
    # the gateway's direct fallbacks apply after these. The models are changed in the AI settings.
    "hermes_agent": _task("Hermes · Instagram Agent (analysis, proposals, skills)", "chat",
                          [("jarvis", "CLAUDE_OPUS_5_5"), ("jarvis", "CLAUDE_SONNET_5_5"), ("arvancloud", "Claude-Opus-4.7")], "editing_agent"),
    "hermes_chat": _task("Hermes · Agent Chat", "chat",
                         [("jarvis", "CLAUDE_SONNET_5_5"), ("jarvis", "CLAUDE_OPUS_5_5"), ("arvancloud", "Claude-Sonnet-4.6")], "general_chat"),
    "segment_analysis": _task("Segment Analysis", "chat", LIGHT, "editing_agent"),
    "transcript_correction": _task("Transcript Correction", "chat", LIGHT, "subtitles"),
    # Long-video discovery (creative/discovery.py): one card per stage so each can be tuned on its own.
    "long_video_enhance": _task("Long Video · Transcript Enhancement", "chat", LIGHT, "subtitles"),
    "long_video_outline": _task("Long Video · Topic Outline", "chat", STORY, "editing_agent"),
    "long_video_clip_finder": _task("Long Video · Clip Finder", "chat", POWER, "editing_agent"),
    "long_video_clip_validator": _task("Long Video · Clip Validator", "chat", POWER, "editing_agent"),
    # Social-reference analysis (creative/reference.py): frame-by-frame review and the overall style description.
    "reference_frame_review": _task("Social Reference · Frame Review", "vision", VISION, "video_understanding"),
    "reference_style_analysis": _task("Social Reference · Style Analysis", "vision", VISION, "video_understanding"),
    # Motion graphics from chat (creative/motion_graphic.py): the designer writes the whole clip, the repair route fixes what the checks report.
    "motion_graphic_planner": _task("Motion Graphic · Planner", "chat", STORY, "editing_agent"),
    "motion_graphic_designer": _task("Motion Graphic · Scene Designer", "chat", POWER, "editing_agent"),
    "motion_graphic_repair": _task("Motion Graphic · Repair", "chat", STORY, "editing_agent"),
    # Script engine (creative/script.py): writer, independent critic, rewrite.
    "script_writer": _task("Script Engine · Writer", "chat", POWER, "editing_agent"),
    "script_critic": _task("Script Engine · Critic", "chat", POWER, "editing_agent"),
    "translation": _task("Translation", "chat", STORY, "subtitles"),
    "subtitle_formatting": _task("Subtitle Formatting", "chat", LIGHT, "subtitles"),
    "script_generation": _task("Script Generation", "chat", STORY, "editing_agent"),
    "image_editing": _task("Image Editing", "image", [("jarvis","GPT_IMAGE_2_5_SUNBURST")], "image"),
    "photorealistic_image": _task("Photorealistic Image", "image", [("jarvis","GPT_IMAGE_2_5_SUNBURST"), ("sarovi","bytedance-seed/seedream-5-0-pro")], "image"),
    "creative_image": _task("Creative Image", "image", [("sarovi","google/gemini-3-pro-image"), ("sarovi","bytedance-seed/seedream-5-0-pro")], "image"),
    "storyboard_image": _task("Storyboard Image", "image", [("jarvis","gemini-3-1-flash-image"), ("sarovi","google/gemini-3.1-flash-image")], "image"),
    "product_video": _task("Product Video", "video", [("sarovi","bytedance/seedance-2.5")], "video"),
    "cinematic_video": _task("Cinematic Video", "video", [("sarovi","openai/sora-2-pro"), ("sarovi","google/veo-3.1")], "video"),
    "fast_broll": _task("Fast B-roll", "video", [("sarovi","bytedance/seedance-2.0-fast"), ("sarovi","google/veo-3.1-fast")], "video"),
    "image_to_video": _task("Image-to-Video", "video", [("sarovi","kwaivgi/kling-v3.0-std"), ("sarovi","bytedance/seedance-2.5")], "video"),
    "narration": _task("Narration / TTS", "speech", [("sarovi","elevenlabs/eleven-v4")], "audio"),
    # No registered Scribe/embedding pair was discovered; do not invent one.
    "transcription": _task("Transcription", "transcription", [], "transcription"),
    "music_generation": _task("Music Generation", "music", [("sarovi","google/lyria-3-clip-preview")], "audio"),
    "embeddings": _task("Embeddings", "embeddings", [], "embeddings"),
}
