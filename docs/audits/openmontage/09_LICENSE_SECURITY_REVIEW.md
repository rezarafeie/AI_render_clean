# 09 — Licence and Security Review

**Not legal advice. Items marked ⚖ need counsel before any implementation that touches them.**

## 1. Licences found

| Item | Evidence | Terms |
| --- | --- | --- |
| OpenMontage | `LICENSE` is the GNU AGPL-3.0 text | AGPL-3.0 |
| `.agents/skills/manimce-best-practices`, `manimgl-best-practices` | own `LICENSE.txt` | per file (not read here) ⚖ |
| `ink-theater/` | `THIRD_PARTY_NOTICES.md` | mixed; not read in full ⚖ |
| Other `.agents/skills/*` (93 folders: hyperframes, remotion, gsap, three.js, ElevenLabs, FLUX, …) | no top-level licence per folder found | upstream licences unknown from the clone; **do not assume they inherit or escape AGPL** ⚖ |
| OpenAI CLIP (model used by `lib/clip_embedder.py`) | upstream project | MIT (to verify at integration time) |

## 2. AGPL-3.0 implications for EditorGPT

* EditorGPT is a network service. AGPL §13 requires offering Corresponding Source to remote users of a *modified* AGPL work. If EditorGPT incorporated OpenMontage code (even behind an API inside the same product) and were judged a derivative/combined work, the obligation could extend to EditorGPT's source. ⚖
* Isolating code behind an HTTP boundary does **not** by itself remove obligations: whether two programs form one work depends on how they are combined; the safe course is to avoid combining.
* Distinguish:
  * **Direct code reuse** (copy/vendor/import): prohibited by this plan.
  * **Instruction/prompt/YAML text reuse** (`skills/**`, `styles/*.yaml`, manifests): copyrightable text; treat like code. Prohibited by this plan.
  * **Independent reimplementation of concepts** (e.g. "score plans for repeated layouts"): ideas and methods are not protected by copyright; write from scratch, from EditorGPT's own failure data, with no side-by-side copying. **This plan's only route.**
  * **Facts** (−14 LUFS, safe-zone pixels, BPM ranges): not copyrightable; already present in EditorGPT.
  * **External service integration** (calling provider APIs): independent of OpenMontage; EditorGPT does it through its router.
  * **Third-party dependency reuse** (numpy, Pillow…): governed by those licences, not by OpenMontage's.
* Clean-room hygiene recommended: implementer reads this audit's descriptions, not OpenMontage source, when writing `plan_checks.py`; record that in the PR description.

## 3. Security findings (source greps; not a full audit)

| Finding | Evidence | Relevance |
| --- | --- | --- |
| `.env` auto-loaded into `os.environ` at import | `tools/base_tool.py::_load_dotenv` | credential exposure model differs from EditorGPT; not applicable if nothing is imported |
| Subprocess use; `shell=True` appears only in comments (2 hits, both explanatory) | grep | low |
| `eval(`/`exec(` outside tests: 2 hits (not inspected) | grep | review if ever consuming code ⚖ |
| 91 files make network calls (provider APIs, downloads, `video_downloader`, `transcript_fetcher`) | grep | would violate EditorGPT's router/no-bypass guard if imported |
| `npx remotion render`, `npm install` flows | `tools/video/remotion_caption_burn.py`, `tools/tool_registry.py` | supply-chain surface; not adopted |
| External CLI `minicut` with a paid approval flow | `tools/minicut_cli.py`, `tools/audio/minicut_*.py` | not adopted |
| Third-party skills fetched/vendored from skills.sh | `.agents/skills` | provenance unclear |

## 4. Requirements before implementation

1. Owner/counsel decision on the clean-room approach (⚖).
2. Never copy `skills/**`, `styles/*.yaml`, `pipeline_defs/*.yaml`, `lib/*.py`, `tools/**` into EditorGPT.
3. Keep `tests/test_no_router_bypass.py` green; no new provider origins.
4. No secrets in audit or evidence files (none were read or written).
