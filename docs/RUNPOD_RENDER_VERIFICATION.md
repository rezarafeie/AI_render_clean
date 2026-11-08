# RunPod development verification — 2026-11-07 to 2026-11-08

## Private Linux worker candidate

The [GitHub Actions build](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42399445489)
published the candidate below. The Linux non-root runtime import and required
executables check passed. The default GitHub-runner Docker namespace probe
failed; this digest is **not approved for cloud admission**. The registry refused
an anonymous pull-token request (HTTP 401).

```text
ghcr.io/rezarafeie/editorgpt-runpod-worker-build@sha256:d514a27d6915f08fc70a4df4ef9513e4a4948b8f536c68901aa6d2692500a28f
```

Private-registry authentication ID transport passed mocked provider/relay tests
(64 focused Python tests and the Node relay test). The authenticated Vercel relay
also verified the registry reference in the live RunPod API account. This checks
the reference, not the image pull.

Branch: `feat/runpod-render-infrastructure-20261107`, based on main `fafcf6e`.
The production EditorGPT app has not been deployed with cloud admission enabled.
An independent VPS smoke test of the private R2 bucket verified signed PUT/GET,
matching content, and cleanup.

## Live CPU canary provisioning

The RunPod v2 catalog returned a Secure Cloud quote of USD 0.060/hour for
`cpu3c` with two vCPUs. Requests with a 30 GB ephemeral disk were rejected
(v1 HTTP 500, v2 HTTP 400 classified as resource configuration). A v2 request
with a 20 GB ephemeral disk reached the provider's billing check and returned
HTTP 402 before account funding.

After funding, the same 20 GB configuration was accepted (HTTP 201). The
container returned the expected probe record, confirming that RunPod pulled
the pinned private GHCR image and ran its entrypoint. The record reported
`network_containment_passed: false`. The probe emits only a boolean, so this
run did not isolate the failing syscall or policy. The provider reported
USD 0.060/hour. Deletion returned HTTP 204 and a follow-up listing confirmed
the canary Pod was absent. This is a provisioning and containment test, not a
render benchmark or an invoice measurement. Cloud admission stays disabled.

The [second private build](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42411562220)
passed the non-root Docker socketless probe. The same immutable image passed
the socketless probe on a RunPod CPU Pod. The separate network namespace check
still returned false. RunPod quoted USD 0.060/hour. Deletion returned HTTP 204
and the Pod was absent on follow-up listing. A non-root Linux VPS probe also
passed the socketless test. These checks cover the inherited egress filter,
not render parity or browser isolation.

The synthetic MLT end-to-end smoke test used the existing application renderer,
one CPU Pod, a pinned private image, the existing queue ledger and private R2.
It produced 90 frames at 320×180, 30 fps, with identical video/audio start times
and durations across the VPS and RunPod. FFmpeg measured SSIM 0.997924 for the
decoded video. The decoded PCM hashes were identical. The cloud encode stage
took 1.40 s. End-to-end was 50.61 s on RunPod versus 12.57 s on the resource-
limited local VPS container. The benchmark is too short to certify production
routing or infer that RunPod is faster for representative jobs. The RunPod
allocation was removed and its absence independently verified. The test
deleted its signed-mailbox objects and dedicated synthetic input objects.

The [MLT-only worker](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42412610879)
also completed a 60-second Persian-captioned synthetic job at 640×360 and 30 fps.
Both outputs contained 1,800 frames and passed media metadata parity. RunPod
spent 28.29 s in the render stage and 128.57 s end-to-end. The prepared reference
ran on the Mac in 46.33 s, so this is a comparison against that reference and
not a VPS performance benchmark. The initial font-unpinned run measured SSIM
0.973844 overall, 0.995282 above the caption area and 0.939203 in the lower
region. Decoded audio hashes differed, but the aligned mono PCM correlation
was 0.999994. This profile has not been approved for routing.

With the exact Vazirmatn font staged alongside the same input, the second
60-second run reached SSIM 0.992632 overall and 0.988513 in the lower subtitle
region. Frame count and media timing again passed. RunPod took 27.77 s to
render and 65.40 s end-to-end. The Mac reference took 56.63 s. The difference
between the two cloud end-to-end times illustrates provisioning variability.
The actual provider charge was not recorded in the benchmark report.

A separate live cancellation canary observed the MLT job enter `rendering`,
issued cancellation through the existing coordinator, and verified a terminal
`cancelled` state. The provider inventory independently confirmed the dedicated
Pod was absent. The canary deleted its synthetic staged objects.

The [host diagnostic candidate](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42438500616)
confirmed that a Secure Cloud `cpu3c` host denies both user and network
namespace creation. Its inherited socketless filter still passed. The host
reported Landlock ABI 4 and seccomp notification support. The diagnostic
could not duplicate a child socket with `pidfd_getfd`. The Pod was deleted
and its absence confirmed in the RunPod API.

An independent VPS reconciliation timer is active. It is scoped to the
production render ledger and skips execution until that ledger exists. A
separate readiness ledger verified access to the private R2 test bucket and
the authenticated RunPod relay. It returned zero resources and recovery jobs.
The R2 bucket's public development URL is disabled. Its only lifecycle rule
aborts incomplete multipart uploads, so staged objects have no automatic TTL.

The [isolated Linux boot check](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42439127328)
passed in a non-root Docker container with the host socketless filter. The
Linux guest could use loopback and had no network device or default route.
This boot check does not certify a Chromium render or the target RunPod host.

The [offline browser diagnostic](https://github.com/rezarafeie/editorgpt-runpod-worker-build/actions/runs/42440557503)
then rendered a one-second, 320×180 HyperFrames fixture inside the guest.
FFprobe verified 30 frames at 30 fps. Docker networking was disabled and the
guest had loopback only. The CI test took approximately 122 seconds, including
guest boot and verification, on a two-CPU container. The sample had no audio.
This establishes basic browser rendering in the guest on the CI host. It
does not establish real RunPod timing, visual parity or a routing profile.

The live VPS checkout is based on `ac81e30` and has tracked local modifications
in Studio, Talking styles and the server Compose overlay. The RunPod branch
base `fafcf6e` is a descendant, 283 commits ahead. The tests ran in an isolated
runner with synthetic assets. Production deployment must reconcile the server's
working changes before replacing its runtime.

## Executed checks

* Current targeted Python suite: **95 passed** across render cloud and creative
  resources. Current relay and cloud settings tests: **3 passed**. The
  TypeScript and Vite production build passed.
* Latest full Python suite: **1064 passed, 4 skipped**, 81.64 seconds. Existing
  deprecation warnings only. Run with cloud disabled and DATABASE_URL empty;
  localhost/MLT tests require permission outside the restrictive sandbox.
* Latest focused cloud + component-gallery suite after restart-recovery and
  read-only preflight changes (including the subsequently added CLI ordering
  regression, canary preflight, namespace command and WebM benchmark checks):
  **79 passed**, 2.73 seconds.
* Frontend serial Node test suite: **131 passed**, no failures/skips.
* `npm run build`: TypeScript + Vite successful; existing chunk-size warnings.
* `git diff --check`: clean.
* Fingerprinted `engine/remotion_renderer.py`: identical to main. No gallery
  receipt/hash regeneration or upstream rendering-engine rewrite.
* Reaper/benchmark CLI `--help`: successful; no provider request.
* Doctor CLI correctly exits 2 with missing configuration, no network/state
  mutation and no credential/path leakage. Fresh worker snapshots are tested
  before idle reconciliation; incomplete upload receipts cannot release compute.
* Canary preflight separates setup from admission certification. The containment
  probe fails closed on the macOS development host; real namespace execution
  still needs a Linux container host and a repeat check on the target worker.

Tests cover mocked REST/S3 workflows, existing authentication/administrator
ceilings, cross-user rejection, leases/concurrent budgets, expired/replayed worker
tokens, unknown create recovery, deletion failures, exact resource ownership,
idempotent billing, real local process timeout/cancellation, synthetic FFmpeg media
and FFprobe checks, recovered output without a second Pod, engine adapters,
Talking cinematic identity sets, bounded cancellable transfer retry, cgroup
metrics and profile format/features/GPU gates. Mocks do not certify RunPod or S3.

## Changed-file inventory

New infrastructure modules under `app/render_cloud/`:
`__init__.py`, `contracts.py`, `prepare.py`, `policy.py`, `settings.py`,
`ledger.py`, `provider.py`, `coordinator.py`, `storage.py`, `transfer.py`,
`mailbox.py`, `supervisor.py`, `worker.py`, `runner.py`, `engines.py`,
`resources.py`, `service.py`, `hooks.py`, `reaper.py`, `parity.py`,
`benchmark.py`, `admin.py`, `doctor.py`, `isolation.py`, `containment_probe.py`.

Existing integration points:
`app/jobs.py`, `app/main.py`, `app/motion_graphic.py`, `app/talking_reel.py`,
`engine/render.py`, `engine/hyperframes/renderer.py`,
`engine/hyperframes/standalone.py`, `engine/hyperframes/product_reel.py`,
`web/src/Settings.tsx`, `web/src/api.ts`, `.gitignore` (track the cloud test only).

New UI/tests/deployment:
`web/src/settings/CloudRender.tsx`, `web/tests/cloud-render-admin.test.mjs`,
`tests/test_render_cloud.py`, `requirements-runpod.txt`,
`deploy/runpod/Dockerfile`, `deploy/runpod/benchmark-suite.json`,
`deploy/runpod/editorgpt-render-reaper.service`,
`deploy/runpod/editorgpt-render-reaper.timer`,
`deploy/runpod/editorgpt-render-billing.service`,
`deploy/runpod/editorgpt-render-billing.timer`, and the three RUNPOD_RENDER docs.

## Unverified acceptance gates

Live validation requires diagnosing the failed containment check and
benchmarking authorized representative projects on hosts that support the
required isolation and resource limits.
Follow RUNPOD_RENDER_ROLLOUT.md.

Direct browser-to-object-store uploads and object-native delivery remain outside
the connected compatibility path. Serverless and verified GPU profiles remain
deferred, not simulated. Representative benchmark results and provider costs are
unknown; no production-ready claim is made. Local rendering remains operational.
