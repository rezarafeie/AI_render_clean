import pytest
from brain.lm_tasks import TASKS, qualified_id


def test_preserves_execution_identity():
    assert qualified_id("jarvis", "CLAUDE_OPUS_5_5") == "custom:CLAUDE_OPUS_5_5#jarvis-all-models"
    assert qualified_id("sarovi", "openai/sora-2-pro") == "custom:openai/sora-2-pro#sarovi-all-models"
    assert qualified_id("google", "gemini-2.5-flash") == "google:gemini-2.5-flash"


@pytest.mark.parametrize("mid", ["", "x#other", "custom:x", "google:x", "x y"])
def test_rejects_injected_scope(mid):
    with pytest.raises(ValueError): qualified_id("jarvis", mid)


def test_policy_is_not_activation_evidence():
    assert len(TASKS) == 45
    assert TASKS['conversation_response']['parent'] == 'general_chat'
    for task in TASKS.values():
        assert "verified" not in task and "enabled" not in task
        assert len({p["id"] for p in task["preferences"]}) == len(task["preferences"])
    assert TASKS["transcription"]["preferences"] == []
    assert TASKS["embeddings"]["preferences"] == []
    assert all("vercel" not in p["id"] for t in TASKS.values() for p in t["preferences"])


def test_priority_is_jarvis_then_sarovi_then_arvan_with_google_first_for_gemini():
    from brain.lm_tasks import prioritize, rank, provider_of
    ids = ["auto", "custom:a#arvancloud-all-models", "custom:b#sarovi-all-models", "custom:c#jarvis-all-models",
           "google:gemini-3.5-flash", "custom:d#openai-all-models", "custom:e#jarvis-all-models"]
    assert prioritize(ids) == ["google:gemini-3.5-flash", "custom:c#jarvis-all-models", "custom:e#jarvis-all-models",
                               "custom:b#sarovi-all-models", "custom:a#arvancloud-all-models", "custom:d#openai-all-models", "auto"]
    assert provider_of("custom:x#sarovi-all-models") == "sarovi" and rank("auto") > rank("custom:d#openai-all-models")


def test_every_task_lists_its_preferences_in_priority_order():
    from brain.lm_tasks import rank
    for key, task in TASKS.items():
        ranks = [rank(p["id"]) for p in task["preferences"]]
        assert ranks == sorted(ranks), key


def test_new_feature_routes_exist_with_the_expected_capability():
    for key in ("long_video_enhance", "long_video_outline", "long_video_clip_finder", "long_video_clip_validator",
                "script_writer", "script_critic"):
        assert TASKS[key]["capability"] == "chat"
    assert TASKS["reference_frame_review"]["capability"] == TASKS["reference_style_analysis"]["capability"] == "vision"


def test_new_routes_are_seeded_by_priority_and_the_prioritize_endpoint_only_reorders(tmp_path, monkeypatch):
    from app.config import settings
    from app import lm_store as store
    from brain import lm_gateway as gateway
    from app.routers import lm_admin
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path))
    routes = gateway.defaults()
    finder = routes["long_video_clip_finder"]
    assert finder["models"][0].endswith("#jarvis-all-models") and finder["models"][1].endswith("#arvancloud-all-models")
    assert routes["long_video_enhance"]["models"][0] == "google:gemini-3.5-flash"        # Gemini goes to Google first
    assert "script_writer" in routes and "reference_frame_review" in routes
    shuffled = dict(routes["creative_director"], models=["auto", "custom:Claude-Opus-4.7#arvancloud-all-models", "custom:CLAUDE_OPUS_5_5#jarvis-all-models"])
    store.save("routes", {"creative_director": shuffled})
    result = lm_admin.prioritize_routes()
    assert "creative_director" in result["routes_changed"]
    assert store.records("routes")["creative_director"]["models"] == [
        "custom:CLAUDE_OPUS_5_5#jarvis-all-models", "custom:Claude-Opus-4.7#arvancloud-all-models", "auto"]
    assert result["direct_order"][:3] == ["jarvis", "sarovi", "arvan"]
