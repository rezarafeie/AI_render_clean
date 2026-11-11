"""The music director: the order of its sources, what it reports, rights, cost preference, emotional arc, and how chat, directives and the Edit tab reach it."""
import json
import shutil

import pytest

from app import motion_graphic as app_mg
from app import motion_edit
from creative import directives
from creative.audio import music_director as md, music_providers as mp
from tests.audio_fixtures import song

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSIC_STORE", str(tmp_path / "store"))
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_PROXY_URL", "STABILITY_API_KEY", "JAMENDO_CLIENT_ID", "EPIDEMIC_SOUND_API_KEY", "MUSIC_DAILY_GENERATIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(md, "library_tracks", lambda: [])


def fake_track(tmp_path, name="energetic electronic drive", tags=("energetic", "electronic"), seconds=60.0):
    path = tmp_path / f"{name.replace(' ', '-')}.mp3"
    path.write_bytes(b"ID3" + b"\0" * 64)
    return {"path": str(path), "filename": name, "tags": list(tags), "mood": " ".join(tags), "duration_sec": seconds, "source": "library"}


# ── arc and prompt ──────────────────────────────────────────────────────────────────────────────────────────────
def test_the_emotional_arc_tiles_the_film_and_puts_its_climax_on_the_reveal():
    arc = md.emotional_arc(45.0, "energetic", accent_s=36.0)
    assert arc[0]["start_s"] == 0.0 and arc[-1]["end_s"] == 45.0 and all(a["end_s"] == b["start_s"] for a, b in zip(arc, arc[1:]))
    assert arc[-1]["start_s"] == 36.0 and arc[-1]["energy"] == 1.0 and "reveal" in arc[-1]["label"]
    assert md.emotional_arc(30.0, "minimal", accent_s=22.0) == [{"start_s": 0.0, "end_s": 30.0, "label": "soft bed", "energy": 0.2}]       # a calm style does not invent a climax


def test_the_style_comes_from_the_words_in_any_language_and_the_prompt_says_what_a_generator_needs():
    assert md.pick_style("a luxury watch teaser") == "luxury" and md.pick_style("ویدیوی آموزشی دربارهٔ چای") == "educational" and md.pick_style("energetic promo") == "energetic"
    assert md.pick_style("") == "commercial" and md.pick_style("x", energy=0.9) == "energetic"
    request = md.MusicRequest(brief="promo", words="synth", duration_s=45, energy=0.9, accent_s=36.0, instruments="analog synth")
    arc = md.emotional_arc(45, "energetic", 36.0)
    prompt = md.build_prompt(request, "energetic", arc)
    assert "BPM" in prompt and "instrumental, no vocals" in prompt and "analog synth" in prompt and "36-45s the reveal" in prompt
    low, high = md.target_bpm("energetic", 1.0)
    assert 120 <= low < high <= 156


# ── order of sources ────────────────────────────────────────────────────────────────────────────────────────────
def test_an_attached_track_is_used_as_it_is_and_a_missing_one_is_never_replaced(tmp_path):
    own = fake_track(tmp_path, "mine")
    chosen = md.resolve(md.MusicRequest(mode="attached", path=own["path"], name="mine.mp3", duration_s=30))
    assert chosen.source == "attached" and str(chosen.path) == own["path"]
    gone = md.resolve(md.MusicRequest(mode="attached", path=str(tmp_path / "nothing.mp3"), duration_s=30))
    assert gone.path is None and gone.notes


def test_a_fitting_library_track_is_reused_and_nothing_is_generated(tmp_path, monkeypatch):
    track = fake_track(tmp_path)
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    monkeypatch.setattr(mp, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("generated although the library fits")))
    monkeypatch.setattr(mp, "search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched although the library fits")))
    chosen = md.resolve(md.MusicRequest(brief="energetic promo", words="energetic electronic", duration_s=30, energy=0.8))
    assert chosen.source == "library" and chosen.label == "energetic electronic drive" and chosen.reasons


def test_without_a_fit_a_catalogue_track_with_rights_is_downloaded_and_one_without_rights_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "cid")
    good = {"id": "jamendo:1", "provider": "jamendo", "source": "search", "title": "Open", "artist": "A", "duration_s": 120, "tags": ["energetic"], "rights": {"ok": True, "reason": "cc-by"},
            "license": {"attribution": "“Open” by A (Jamendo)"}, "download_url": "https://dl/1.mp3"}
    bad = {**good, "id": "jamendo:2", "title": "NC", "rights": {"ok": False, "reason": "cc-by-nc forbids commercial use"}}
    monkeypatch.setattr(mp, "search", lambda *a, **k: {"tracks": [bad, good], "skipped": [{"provider": "epidemic", "reason": "EPIDEMIC_SOUND_API_KEY is not set"}]})
    file = tmp_path / "dl.mp3"
    file.write_bytes(b"ID3" + b"\0" * 64)
    monkeypatch.setattr(mp, "fetch", lambda track, **k: {**track, "path": str(file)})
    chosen = md.resolve(md.MusicRequest(brief="x", words="energetic", duration_s=60, mode="search"))
    assert chosen.source == "search" and chosen.attribution == "“Open” by A (Jamendo)" and str(chosen.path) == str(file)
    assert any("epidemic" in n for n in chosen.notes) and any("NC" in r and "commercial" in r for r in chosen.reasons)


def test_generation_is_the_last_resort_costs_nothing_to_reuse_and_respects_the_cost_preference(tmp_path, monkeypatch):
    calls = []
    out = tmp_path / "gen.mp3"
    out.write_bytes(b"ID3" + b"\0" * 64)

    def fake_generate(prompt, seconds, **kw):
        calls.append((prompt, seconds, kw))
        return {"id": "generated:k", "provider": "elevenlabs", "source": "generated", "title": prompt[:30], "path": str(out), "duration_s": seconds, "prompt": prompt, "cache_hit": False,
                "license": {"name": "x"}, "cost": {"usd": 0.08}, "rights": {"ok": True, "reason": "ok"}}
    monkeypatch.setattr(mp, "generate", fake_generate)
    chosen = md.resolve(md.MusicRequest(brief="energetic promo", words="energetic synth", duration_s=45, energy=0.9, accent_s=36.0))
    assert chosen.source == "generated" and chosen.cost == {"usd": 0.08} and len(calls) == 1
    assert "36-45s the reveal" in calls[0][0] and calls[0][1] >= 45 and calls[0][2]["instrumental"] is True
    calls.clear()
    free = md.resolve(md.MusicRequest(brief="energetic promo", words="energetic synth", duration_s=45, cost="free"))
    assert not calls and any("رایگان" in n for n in free.notes) and free.path is None
    strict = md.resolve(md.MusicRequest(brief="promo", duration_s=45, strict=True))
    assert not calls and strict.path is None


def test_an_explicit_generate_skips_the_library_and_a_failing_generator_falls_back_to_the_closest_track(tmp_path, monkeypatch):
    track = fake_track(tmp_path)
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    monkeypatch.setattr(mp, "generate", lambda *a, **k: (_ for _ in ()).throw(mp.MusicError("no_credentials", "ELEVENLABS_API_KEY is not set")))
    chosen = md.resolve(md.MusicRequest(brief="x", words="energetic electronic", duration_s=30, mode="generate"))
    assert chosen.source == "fallback" and chosen.label == track["filename"]
    assert any("no_credentials" in n for n in chosen.notes) and any("نزدیک‌ترین" in n for n in chosen.notes)


def test_variants_do_not_repeat_the_track_just_heard(tmp_path, monkeypatch):
    a, b = fake_track(tmp_path, "energetic electronic one"), fake_track(tmp_path, "energetic electronic two")
    monkeypatch.setattr(md, "library_tracks", lambda: [a, b])
    first = md.resolve(md.MusicRequest(brief="x", words="energetic electronic", duration_s=30))
    second = md.resolve(md.MusicRequest(brief="x", words="energetic electronic", duration_s=30, variant=1, exclude=[str(first.path)]))
    assert str(first.path) != str(second.path)


def test_premium_prefers_fresh_music_over_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(md, "library_tracks", lambda: [fake_track(tmp_path)])
    out = tmp_path / "gen.mp3"
    out.write_bytes(b"ID3" + b"\0" * 64)
    monkeypatch.setattr(mp, "generate", lambda prompt, seconds, **k: {"id": "generated:z", "provider": "elevenlabs", "source": "generated", "title": "t", "path": str(out), "duration_s": seconds,
                                                                      "prompt": prompt, "cache_hit": False, "license": {}, "cost": {}, "rights": {"ok": True, "reason": ""}})
    chosen = md.resolve(md.MusicRequest(brief="x", words="energetic electronic", duration_s=30, cost="premium"))
    assert chosen.source == "generated"


@needs_ffmpeg
def test_sound_effect_moments_are_the_cuts_and_the_reveal_only():
    moments = md.sfx_moments([{"start": 0.0}, {"start": 4.0}, {"start": 9.0}], {"drops_ms": [9000, 15000]}, 9.0)
    kinds = sorted((m["kind"], m["time_ms"]) for m in moments)
    assert kinds == [("accent", 15000), ("reveal", 9000), ("transition", 4000), ("transition", 9000)]


# ── words, directives, edits ────────────────────────────────────────────────────────────────────────────────────
def test_what_a_request_says_about_music_is_understood_without_false_alarms():
    assert md.music_wanted("Create a 45-second energetic promotional reel. Find or generate suitable music, synchronize cuts to the beat")
    assert md.music_wanted("ویدیویی با موسیقی پرانرژی بساز")
    assert not md.music_wanted("a film about music education") and not md.music_wanted("Scene 1: music for everyone") and not md.music_wanted("no music please")
    assert md.edits_from_text("make the music calmer") == {"energy_delta": -0.25}
    assert md.edits_from_text("موسیقی را عوض کن") == {"regenerate": True}
    assert md.edits_from_text("turn off beat sync") == {"sync": False}
    assert md.is_music_only("make the music calmer") and not md.is_music_only("change the headline to Hello and make the music calmer")


def test_music_directives_choose_the_source_and_options_and_keep_the_old_forms():
    parse = lambda text: directives.parse(text)[1]
    legacy = parse("Music: library, cinematic minimal")
    assert (legacy.music, legacy.music_words, legacy.music_sync) == ("library", "cinematic minimal", None)
    auto = parse("Music: auto")
    assert auto.music == "auto" and auto.music_words == ""
    made = parse("Music: generate energetic synth, no vocals, premium")
    assert (made.music, made.music_cost, made.music_instrumental) == ("generate", "premium", True)
    assert parse("Music: search calm piano no sync").music_sync is False and parse("موسیقی: بساز پرانرژی روی بیت").music == "generate"


def test_create_decides_the_music_from_directives_words_and_attachments(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mg, "ROOT", tmp_path)
    plain = app_mg.create("c", "u", "A film about tea.")
    assert plain["music"] is None and plain["rhythm"] == "speech_first"
    asked = app_mg.create("c", "u", "A 45-second promo. Find or generate suitable music, synchronized to the beat.")
    assert asked["music"]["mode"] == "auto" and asked["music"]["sync"] is True and asked["rhythm"] == "balanced" and asked["music"]["cost"] == "balanced"
    legacy = app_mg.create("c", "u", "Music: library, calm\nA film.")
    assert legacy["music"]["mode"] == "library" and legacy["music"]["sync"] is False and legacy["rhythm"] == "speech_first"
    track = tmp_path / "t.mp3"
    track.write_bytes(b"ID3")
    sent = app_mg.create("c", "u", "A film.", attachments=[{"kind": "audio", "path": str(track), "filename": "t.mp3"}])
    assert sent["music"]["mode"] == "attached" and sent["music"]["path"] == str(track)
    off = app_mg.create("c", "u", "Music: off\nA film.")
    assert off["music"]["mode"] == "off"


def test_a_sentence_about_the_music_rebuilds_only_the_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mg, "ROOT", tmp_path)
    record = app_mg.create("c", "u", "Music: auto\nA film.")
    directory = app_mg.folder("u", "c", record["id"])
    started = []
    monkeypatch.setattr(app_mg, "start", lambda d, change="": started.append(change))
    app_mg.revise(directory, "make the music calmer")
    after = app_mg.load(directory)
    assert started == [""] and after["music"]["energy"] < (after["audio_plan"]["music_energy"] or 1)         # no designer is asked: only the audio is redone
    app_mg.revise(directory, "change the headline to Hello and make the music calmer")
    assert started[-1].startswith("change the headline")                                                         # a wider request still reaches the designers
    app_mg.revise(directory, "no music")
    assert app_mg.load(directory)["music"] is None


def test_the_edit_tab_lists_the_music_controls_and_applies_them(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mg, "ROOT", tmp_path)
    record = app_mg.create("c", "u", "Music: library, calm\nA film.")
    directory = app_mg.folder("u", "c", record["id"])
    (directory / "plan.json").write_text(json.dumps({"fp": "x", "plan": {"palette": {}, "scenes": [{"headline": "h", "idea": "i", "narration": "n", "start": 0, "end": 4}]}}))
    groups = {g["id"]: g for g in motion_edit.editable(directory, record)["groups"]}
    music = {f["key"]: f for f in groups["music"]["fields"]}
    assert set(music) >= {"music.mode", "music.words", "music.sync", "music.level_db", "music.regenerate"}
    assert {o["value"] for o in music["music.mode"]["options"]} >= {"off", "auto", "library", "search", "generate"}
    advanced = {f["key"] for f in groups["music_advanced"]["fields"]}
    assert advanced >= {"music.style", "music.energy", "music.instrumental", "music.cost", "music.ducking_db", "sfx.level", "mix.rhythm", "mix.loudness"}
    result = motion_edit.apply(directory, record, {"music.mode": "auto", "music.sync": "on", "music.energy": 0.85, "music.cost": "free", "sfx.level": "dynamic", "music.regenerate": "new"})
    assert record["music"]["mode"] == "auto" and record["music"]["sync"] is True and record["music"]["energy"] == 0.85 and record["music"]["cost"] == "free"
    assert record["music"]["variant"] == 1 and record["sfx"] == "dynamic" and record["rhythm"] == "balanced" and result["redo"]["audio"] is True
    with pytest.raises(motion_edit.EditError):
        motion_edit.apply(directory, record, {"music.energy": 3})


def test_agent_tools_find_music_without_secrets_or_side_effects(tmp_path, monkeypatch):
    from app.agents.medium import tools
    track = fake_track(tmp_path)
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    found = tools._find_music(tools.FindMusic(query="energetic electronic", energy=0.8, limit=5))
    assert found["library"][0]["filename"] == "energetic electronic drive" and "path" not in found["library"][0]
    assert {p["provider"] for p in found["providers"]} == {"elevenlabs", "stability", "jamendo", "epidemic"} and not any(p["available"] for p in found["providers"])
    assert found["skipped"] and "rights.ok" in found["note"]
    catalog = {row["name"]: row for row in tools.catalog()}
    assert catalog["find_music"]["requires_approval"] is False and catalog["analyze_music"]["requires_approval"] is False and catalog["generate_music"]["requires_approval"] is True


# ── a reveal accent needs a drop ──────────────────────────────────────────────────────────�
def _generator(tmp_path, calls):
    out = tmp_path / "gen.mp3"
    out.write_bytes(b"ID3" + b"\0" * 64)

    def fake_generate(prompt, seconds, **kw):
        calls.append(prompt)
        return {"id": "generated:k", "provider": "elevenlabs", "source": "generated", "title": prompt[:30], "path": str(out), "duration_s": seconds, "prompt": prompt, "cache_hit": False,
                "license": {"name": "x"}, "cost": {"usd": 0.08}, "rights": {"ok": True, "reason": "ok"}}
    return fake_generate


def test_a_reveal_accent_prefers_a_track_with_a_drop_and_makes_one_when_the_library_has_none(tmp_path, monkeypatch):
    track = fake_track(tmp_path)
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    request = md.MusicRequest(brief="energetic promo", words="energetic electronic", duration_s=45, energy=0.8, accent_s=36.0)
    calls = []
    monkeypatch.setattr(mp, "generate", _generator(tmp_path, calls))
    monkeypatch.setattr(md, "analysis_for", lambda path: {"drops_ms": [], "energy": [0.5]})
    flat = md.resolve(request)
    assert flat.source == "generated" and len(calls) == 1 and any("درآپ" in n for n in flat.notes)
    calls.clear()
    monkeypatch.setattr(md, "analysis_for", lambda path: {"drops_ms": [30000], "energy": [0.5]})
    dropped = md.resolve(request)
    assert dropped.source == "library" and not calls                    # a track that already has a drop is reused, nothing is paid for
    calls.clear()
    plain = md.resolve(md.MusicRequest(brief="energetic promo", words="energetic electronic", duration_s=45, energy=0.8))
    assert plain.source == "library" and not calls                      # no accent asked: the old rule, no analysis needed


def test_without_a_generator_the_flat_track_is_still_used_and_the_reason_is_said(tmp_path, monkeypatch):
    track = fake_track(tmp_path)
    monkeypatch.setattr(md, "library_tracks", lambda: [track])
    monkeypatch.setattr(md, "analysis_for", lambda path: {"drops_ms": [], "energy": [0.5]})
    chosen = md.resolve(md.MusicRequest(brief="energetic promo", words="energetic electronic", duration_s=45, energy=0.8, accent_s=36.0))
    assert chosen.path and chosen.source in {"fallback", "library"} and any("درآپ" in n for n in chosen.notes)
