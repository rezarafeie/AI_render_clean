# RunPod render infrastructure: rollout and rollback

## Status and boundaries

Implemented opt-in integration; **not production enabled or live-certified**.
All cloud flags default off. Existing local engines remain the default. No real
RunPod/S3 benchmark, container build or deployment is claimed by this document.

The existing job orchestration remains authoritative. Prepared engine inputs are
frozen and hashed on the VPS, dispatched to a dedicated CPU/GPU Pod, downloaded
through short-lived object URLs, rendered using the original engine, uploaded,
then independently verified and atomically published by the VPS. AI planning,
narration generation, project permissions and conversation state do not move.
Worker heartbeat/cancel/progress use scoped S3 mailboxes, not a public callback
endpoint. Workers receive neither RunPod credentials nor bucket credentials.

Connected boundaries:

* MLT: `engine/render.py`, preserving the existing renderer and style options.
* HyperFrames page/project/product: existing render functions, including webm
  transparent product layers. HyperFrames stays pinned to the application version.
* Remotion: `app/jobs.py` callsite; the fingerprinted renderer is unchanged.
* Talking styles 1–4: prepared plans/options with authorized asset rebasing.
* Existing progress/cancellation callbacks and output paths are preserved.
* Administrator-only controls are in existing Settings → Tools. Controls cannot
  exceed server environment ceilings. The narrower server user allowlist controls
  actual canary admission, independently of the UI administrator role.

Not every processing operation is offloaded: native precompositions, style-5 final
compositing, unsupported legacy assets and fractional-cadence Talking inputs may
remain local. Unsupported portable inputs fall back only **before** cloud admission.
After uncertain Pod creation there is no silent second/local render.

Compatibility output delivery downloads a completed object once to the VPS, since
existing quality review and FileResponse require local paths. Browser uploads are
unchanged; direct browser-to-S3 and object-native output delivery are **not** wired.
Do not claim zero VPS transfer. Input staging is streamed and user-scoped assets
are content-addressed/deduplicated. No second timeline interpreter is introduced.

## Required secure configuration

Install optional VPS dependencies: `pip install -r requirements-runpod.txt`.
For a containerized control plane, build its existing runtime with
`--build-arg EDITORGPT_RUNPOD_CONTROL_PLANE=1`. Use the default build for the
RunPod worker. The worker uses scoped HTTPS requests and does not need boto3.
Run `python -m app.render_cloud.doctor` for a read-only, credential-redacted
configuration preflight (exit 2 means missing/invalid setup). It creates no files,
performs no network requests and never certifies live readiness.
Use `--phase canary` before the first test: it checks setup without requiring
already measured profiles or sandbox certification. The default admission phase
requires both. Passing either phase does not enable cloud rendering.
Use the existing service secret manager/private environment file; never commit or
paste credentials into chat. S3 credentials use the normal server boto3 chain.

Environment variables (all except the stated aliases use `RENDER_CLOUD_`):

| Variable | Purpose/default |
|---|---|
| `RENDER_CLOUD_ENABLE_CLOUD_RENDER` | false; admission ceiling |
| `RENDER_CLOUD_ENABLE_RUNPOD_CPU` | false |
| `RENDER_CLOUD_ENABLE_RUNPOD_GPU` | false |
| `RENDER_CLOUD_ENABLE_RUNPOD_SERVERLESS` | false; reserved, no Serverless adapter |
| `RENDER_CLOUD_ENABLE_LOCAL_FALLBACK` | true |
| `RENDER_CLOUD_SANDBOX_VERIFIED` | false; set only after the file-based worker passes target-host isolation and resource checks |
| `RENDER_CLOUD_NETWORK_NAMESPACE_VERIFIED` | false; set only after a loopback-only namespace check on the selected worker |
| `RENDER_CLOUD_BROWSER_GUEST_VERIFIED` | false; set only after the selected guest image passes live browser isolation and rendering checks |
| `RENDER_CLOUD_NATIVE_BROWSER_VERIFIED` | false; set only after the selected native worker passes isolation and representative rendering on its target host |
| `RENDER_CLOUD_ADMIN_USER_IDS` | comma-separated authenticated user IDs |
| `RENDER_CLOUD_IMAGE` | immutable `registry/image@sha256:...` |
| `RENDER_CLOUD_CPU_IDS`, `RENDER_CLOUD_GPU_IDS` | verified RunPod resource IDs |
| `RENDER_CLOUD_VCPU`, `RENDER_CLOUD_DISK_GB` | 8, 40 |
| `RENDER_CLOUD_MAX_WORKERS`, `RENDER_CLOUD_MAX_GPU` | 1, 0 |
| `RENDER_CLOUD_MAX_WALL_SECONDS` | 1800 |
| `RENDER_CLOUD_MAX_COST` | USD .50 per reservation |
| `RENDER_CLOUD_DAILY_BUDGET`, `RENDER_CLOUD_MONTHLY_BUDGET` | USD 5, 30 |
| `RENDER_CLOUD_OVERRIDE` | auto/local/runpod_cpu/runpod_gpu |
| `RENDER_CLOUD_LEDGER` | absolute persistent local SQLite file |
| `RENDER_CLOUD_BENCHMARKS` | absolute approved profile JSON path |
| `RENDER_CLOUD_DEPLOYMENT` | resource identity label; default editor |
| `RENDER_CLOUD_S3_BUCKET` | private bucket |
| `RENDER_CLOUD_S3_ENDPOINT`, `RENDER_CLOUD_S3_REGION` | endpoint; region us-east-1 |
| `RENDER_CLOUD_S3_NAMESPACE` | `render/v1/` by default; use `render/production/v1/` for a distinct production lifecycle |
| `RENDER_CLOUD_STORAGE_HOSTS` | exact comma-separated signed-URL hosts |
| `RENDER_CLOUD_RUNPOD_API_KEY` or `RUNPOD_API_KEY` | server-only provider key |
| `ENABLE_CLOUD_REAPER` | 1 for independent cleanup CLI |

If direct RunPod REST access is unavailable, the optional
[Vercel control-plane relay](../deploy/runpod-relay/README.md) uses
`RENDER_CLOUD_RUNPOD_RELAY_URL` and `RENDER_CLOUD_RUNPOD_RELAY_TOKEN`.
Set both in the backend, reaper and billing environments. S3 stays direct and
still requires separate endpoint and bucket/volume configuration.
For a private GHCR image, register pull-only credentials in RunPod's Container
Registry Auth and set only its ID as `RENDER_CLOUD_RUNPOD_REGISTRY_AUTH_ID`
on EditorGPT. The RunPod provider and relay must both include this allowlisted
field; deploy the updated relay before attempting a private image pull.

The RunPod Pod creation API does not offer a provider-enforced termination
deadline. The former `runpodctl pod create --terminate-after` flag was removed
because it did not work. The independent reaper can request deletion and retry
after a failure, but cannot bound billing during a control-plane outage. A canary
requiring a hard deadline must stay unprovisioned unless the provider offers a
verified expiry mechanism. See [RunPod CLI change #330](https://github.com/runpod/runpodctl/pull/330).

Ledger/profile defaults are under the existing JOBS_DIR/cloud-render directory.
SQLite requires shared persistent **local disk on one VPS**, not NFS or independent
multi-VPS copies. Include it in backups and retain it across application releases.
The private bucket needs signer-scoped object read/write/HEAD permissions and a
lifecycle expiration policy for bootstrap, status/control, candidate and staging
objects. Scope the policy to `render/production/v1/` when using the production
namespace. Choose retention beyond maximum job/recovery time; never public-read.
Configure storage billing/retention independently; deleted compute is not free
object storage. No browser CORS policy is required by the implemented server path.

## Build and containment gate

Build the existing complete EditorGPT runtime, including fonts, Chromium, melt,
FFmpeg, pinned HyperFrames, Remotion and vendored native-library assets. Push it
and use its digest, then build/push the small non-root overlay:

```sh
docker build -f deploy/runpod/Dockerfile \
  --build-arg EDITORGPT_RUNTIME=REGISTRY/RUNTIME@sha256:DIGEST \
  -t REGISTRY/RENDER:canary .
```

Record the overlay's immutable digest in configuration and benchmark profiles.
Do not bake `.env`, API keys, user media or production databases into either image.
Never mount Docker sockets or production data roots. UID 10001 needs writable
/work. The supervisor strips credentials from child environments and protects
its own process handles. The file-based MLT worker runs under an
inherited seccomp filter that denies network sockets, external Unix sockets and
alternative socket syscalls. Chromium-based engines, including Talking styles
that may use Tscaps overlays, need local sockets and a loopback-only network.
Use either a verified namespace (`unshare --user --map-root-user --net`) or
the optional Linux guest. The guest runs QEMU under the socketless host
filter with no NIC, a read-only system disk and only the per-job workspace
shared via 9P. The optional native browser image instead uses a seccomp
notification broker for socket operations and a pinned Chrome Headless Shell.
The broker creates and connects sockets itself and permits only listeners
created by that render. The Node adapter advertises the worker's IPv4 loopback
to Remotion's port discovery. Each path preserves existing render-engine
entrypoints. Each engine still requires an approved profile for the exact image.
For a credential-free network smoke test of the image on a Linux build host:

```sh
docker run --rm --network none --entrypoint python REGISTRY/RENDER:canary \
  -m app.render_cloud.containment_probe --require-socketless
```

Run the same probe inside the target worker environment. The socketless result
checks network syscall denial and filter inheritance. The separate namespace
result checks namespace identity, loopback connectivity and denial of a
non-loopback IPv4 route. For namespace-based browser certification require
that result on the actual host. Neither probe changes admission flags.

If the provider denies namespace creation, build the offline guest from the
immutable worker image, then exercise the smoke target with Docker networking
disabled. Only the smoke target bundles the synthetic fixture.

```sh
docker build -f deploy/runpod/offline-guest.Dockerfile --target smoke \
  --build-arg EDITORGPT_RUNPOD_BASE=REGISTRY/RENDER@sha256:DIGEST \
  -t editorgpt-offline-smoke .
docker run --rm --network none --cpus 2 --memory 4608m --pids-limit 96 \
  --entrypoint python editorgpt-offline-smoke \
  /opt/editorgpt-offline/smoke.py /opt/editorgpt-offline/gsap.min.js
```

Publish the `runtime` target to the private registry only after the local
smoke succeeds. Verify the pinned digest on the target RunPod hardware and
measure a representative workload before admitting browser renders. CPU
emulation has startup and render overhead. Measure the whole job, including
image pull and guest startup, before approving any profile.

Build and check the native browser candidate separately on Linux. The first
command tests loopback access and external socket denial. The second renders
a typed portrait composition with IPv6 disabled, matching the observed RunPod
host constraint.

```sh
docker build -f deploy/runpod/native-browser.Dockerfile \
  --build-arg EDITORGPT_RUNPOD_BASE=REGISTRY/RENDER@sha256:DIGEST \
  -t editorgpt-native-browser .
docker run --rm --network none --memory 384m \
  -v "$PWD/deploy/runpod:/experiment:ro" --entrypoint python editorgpt-native-browser \
  -m app.render_cloud.native_loopback python /experiment/native-loopback-smoke.py
docker run --rm --network none --sysctl net.ipv6.conf.all.disable_ipv6=1 \
  --cpus 2 --memory 3072m --pids-limit 192 \
  -v "$PWD/deploy/runpod:/experiment:ro" --entrypoint python editorgpt-native-browser \
  /experiment/native-browser-smoke.py
```

Verify target CPU, RAM, disk and PID limits, cancellation, deadlines and network
denial on real RunPod before setting SANDBOX_VERIFIED. Include Chromium
descendants in the browser certification. Check provider/container limits
independently of application process-group cleanup.

## Independent cleanup, recovery and cost control

Adapt the sample systemd units in `deploy/runpod/` to actual service user, checkout,
venv, ledger and **all output/work directories**. Their ReadWritePaths must allow
recovery publication, not only SQLite writes. Samples are not installed by code.

* Reaper timer: every minute; progress recovery, deadline/stale/idle cleanup.
* Billing timer: every fifteen minutes; cleanup then measured billing sync.
* Manual emergency: `python -m app.render_cloud.reaper --emergency`.
* Manual billing: `python -m app.render_cloud.reaper --billing`.

Both services need the same private environment and ledger. Alert on nonzero
exit, cleanup_pending, ambiguous create and repeated recovery failure. A random
name+image intent is committed before the single create request. Lost responses
are recovered by exact identity, never a name-prefix account sweep. Ambiguous
inventory retains the reservation rather than creating a replacement Pod.
Fresh authenticated mailbox snapshots are ingested before idle detection; candidate
downloads occur after compute reconciliation. Observation/recovery failures return
nonzero and never print SDK exceptions or signed URLs.
Only dedicated resources recorded in this ledger are eligible for deletion.
After upload receipt the Pod is released before VPS download/quality review.

Reservations enforce concurrency and conservative application budgets; returned
hourly quotes and available memory are checked. Provider bucket charges are
idempotently imported separately from estimates, including failed attempts. The
billing endpoint aggregates Pod compute/storage: the UI does not invent a split
or treat missing charges as zero. Delayed bills, startup before quote rejection,
provider outages and deletion failures mean these are **best-effort application
limits, not a guaranteed provider spending cap**. Keep independent provider alerts.

## Benchmarks and acceptance gates

`deploy/runpod/benchmark-suite.json` lists all eight required cases but intentionally
contains no invented project references. Populate frozen authorized fixture paths.

```sh
python -m app.render_cloud.benchmark deploy/runpod/benchmark-suite.json \
  --backend local --report /ABSOLUTE/local-report.json
# Paid command: only after explicit operator authorization and sandbox canary.
python -m app.render_cloud.benchmark deploy/runpod/benchmark-suite.json \
  --backend runpod_cpu --allow-paid --max-hourly-usd VERIFIED_CEILING \
  --report /ABSOLUTE/cpu-report.json
```

Use identical input hashes/export settings for VPS/CPU/GPU. Reports include actual
elapsed and worker stage times, metadata parity and dedicated-container resource
metrics when available; missing metrics/charges remain unknown. Metadata parity
is not visual/audio certification. Inspect decoded frames, Persian typography,
alpha, effects and audio sync against the local reference. Test application
restart, worker interruption, cancellation, failed uploads/deletion, duplicates
and concurrent budget admission. No genuine GPU-required engine/profile has yet
been verified. Do not substitute a browser composition for that benchmark.

Approved profile JSON is an array of `policy.Benchmark` fields: engine, backend,
width, height, fps, max_duration, end_to_end_seconds, estimated_usd,
parity_verified, image_digest, hourly_usd, hardware_id, export_format, features,
vcpu, min_memory_gb, gpu_acceleration_verified. Require measured positive price,
RAM requirement and exact hardware/image/format/features match. No profiles ship
as approved; benchmark CLI never self-certifies one. GPU requires explicit verified
acceleration. Serverless remains deferred pending operational/economic evidence.

Local validation includes mocked provider/S3 end-to-end tests and real synthetic
FFmpeg/FFprobe/process cancellation tests, not live infrastructure certification.
Remaining external gates: Docker build, optional SDK installation, real S3 signed
transfer, real RunPod namespace/resource canary, representative parity/cost suite,
independent timer installation and operator alerting. Docker was unavailable and
the attempted optional SDK download timed out in this development environment.

## Rollout and rollback

Start with one allowlisted administrator, one worker and a small spending ceiling.
Enable only verified engine profiles after the above gates. Keep GPU/Serverless
off until independently justified. Observe a canary before increasing scope.
No production traffic was switched by this implementation.

Rollback: disable NEW cloud admissions in server configuration/admin controls;
drain or cancel existing executions; keep reaper/billing running until actual
provider deletion is confirmed. Then deploy the prior application image. Existing
local projects/output contracts need no reverse migration. **Never delete the
ledger or stop cleanup while resources/uncertain creates remain outstanding.**
An emergency command is scoped, not an account-wide shutdown guarantee.

Official API references checked 2026-11-07:

* https://docs.runpod.io/api-reference/pods/POST/pods
* https://docs.runpod.io/api-reference/pods/GET/pods
* https://docs.runpod.io/api-reference/pods/DELETE/pods/podId
* https://docs.runpod.io/api-reference/billing/GET/billing/pods
* https://docs.runpod.io/serverless/workers/overview
