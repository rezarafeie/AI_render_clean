# Director: from a fixed orchestrator to a real agent (plan, 2026-11-17)

## 1. Why the chat feels artificial (read from the code)

| Symptom the owner sees | Cause in the code |
|---|---|
| A request is read wrongly | `studio_orchestrator._resolved_intent`: ONE model call picks one of 12 intents from a 40-line prompt full of special cases, then keyword rules (`_intent`, `_style`, `_reference_motion_request`, `_long_video_intent`, ...) override or replace it. A new kind of request needs a new rule. |
| «improve my motions» on a video that is already full of graphics just edits it | Nothing LOOKS at the footage before choosing. `request_brief.understand` runs only for some video requests and only returns a scope enum (translate / find_clips / captions_only / full_edit). |
| Edits all look alike (premium, Vox, motion, the Canva story = the EditorGPT story) | Every engine is a fixed pipeline with ONE prompt template and ONE layout vocabulary. Creativity is limited to choosing a `look` from a list of ten; nothing compares the new film with what this person already got. |
| Endings are bad, voices sound synthetic, motion is repetitive | The only critic is one vision pass over a contact sheet of stills + one revision. Nobody watches the video (cuts, ending, motion), listens to it (pace, silence, voice) or checks it against a rubric. |
| The chat cannot plan, take an edit instruction, discuss | `studio_narrator` writes messages ABOUT tool events; the conversation itself has no planner with memory. `Medium` is opt-in and its graph is plan -> approve -> run steps -> re-plan at most 3 times. |

Root cause in one sentence: **decisions are made once, up front, by a classifier; production is a conveyor belt; nobody looks at the result and decides again.**

## 2. Target: a Director agent (one brain per conversation)

A tool-using loop (native tool calling on the router's `editing_agent` route, Claude Opus first), like Claude Code: it observes, thinks, acts, looks at what it made, and decides the next step. No intent enum; the "route" is whatever tools it calls.

**Perception tools (it looks before it decides)**
- `look(video|image, times?)` frames + transcript + on-screen-text density + «is this raw footage or already produced?» (graphics/subtitle load, cut rate).
- `listen(audio|video)` loudness, silence map, voice/music balance, transcript with word times.
- `read(url)`, `search(web)`, `inspect_project`, `read_history` (this person's earlier outputs).

**Production tools (the existing engines, as capabilities with parameters, not flows)**
- `edit_talking`, `create_film` (vox / intro / motion / premium / 3d), `localize`, `discover_clips`, `revise`, plus `author_scenes` (the agent writes composition code from the kit's primitives directly when no template fits).
- Every tool takes a **concept** (see 3), not just a style name.

**Critic tools (it checks its own work)**
- `review_stills`, `review_video` (frames at every cut, the last 3 s, motion variety, text collisions), `review_audio` (loudness, pace, ending, artefacts), `novelty_check` (against the person's previous films and against the same engine's earlier outputs).

**Chat**
- It talks first: when the request is ambiguous in a way that changes the result it asks ONE good question or offers 2-3 directions with reasons; otherwise it just goes. It can say «send me the raw video, this one already has graphics».
- Plans are negotiable text; edits are instructions on a structured project document. Approval gates only for money, irreversible actions and the final render, never for thinking.

**Safety and cost (unchanged guarantees)**
- Same ownership checks, allow-listed tools, budgets (tokens, credits, render seconds), checkpoints, Stop, retry from checkpoint, the same timeline events. A tool failure is observed by the agent, which chooses another way.

## 3. Creativity that is real, not a menu

Each film starts from a **concept spec** the Director writes (and the person can edit in chat): structure (arc, number and order of beats), signature move, palette, type voice, motion language, transition language, sound design, ending. Engines render the concept; they stop choosing the look themselves.
- `novelty_check` compares the spec's fingerprint (structure + palette + layout recipes + ending kind) with the person's last N films and this engine's recent ones; too close = rewrite the concept.
- Templates become **recipes with free parameters** (layout, scene order, step visuals are chosen by the concept, with `author_scenes` as the escape hatch), so two Story intros share a toolbox but not a skeleton.

## 4. Phases (each one measured, each one reversible)

0. **Eval harness first (this week).** ~40 real requests (the six chats above and recent real ones) with the expected behaviour (route, question or not, what the output must contain). Scored by a rubric + model judge + simple measurable checks (graphics density of input, end hold, text collisions, LUFS). Nothing ships if it does not beat the current system here.
1. **Director in shadow mode.** It runs beside the classifier on every message and only logs what it WOULD do. Compare, fix, learn; no user impact.
2. **Perception first.** `look`/`listen` + «raw or produced?» in front of every video request; the 7aa6-type misunderstanding is fixed here, for real.
3. **Concepts + novelty.** Concept spec, fingerprints, recipe parameters; Story intro, Vox, motion and premium take a concept.
4. **Critics on the real output.** Video + audio review, endings, voice direction (ElevenLabs v3 audio tags, per-line delivery notes, pronunciation pass already shipped), second revision round.
5. **Switch.** Director becomes the default (Lite/Medium picker retired or kept as «classic»), the old classifier stays as a fallback until the eval says it can go.

## 5. Costs and risks (said plainly)
- More model calls per request (observe + critique); mitigated by cheap models for perception, Opus for decisions, caching, and budgets per request.
- A free agent can wander: step and budget limits, a plan the person can see, and the eval harness catches regressions.
- This is weeks of work, not one change. Phases 0-2 give the biggest visible gain per day; 3-4 give the creative leap.
