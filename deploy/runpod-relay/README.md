# EditorGPT RunPod control-plane relay

This standalone Vercel project forwards only the RunPod REST operations used
by EditorGPT: list/create/delete Pods and read daily Pod billing. It cannot
proxy arbitrary URLs or S3 transfers. The caller token grants the ability to
create billable Pods and must be treated as a production secret.

1. In the isolated Vercel project, set **Secret** variables
   `RUNPOD_API_KEY` (prefer a rotated, narrowly scoped RunPod key) and
   `RUNPOD_RELAY_TOKEN` (an independent random value, at least 32 characters).
   Redeploy the same reviewed source after setting them.
2. On the EditorGPT server, set
   `RENDER_CLOUD_RUNPOD_RELAY_URL=https://<verified-project-host>/api/runpod`
   and `RENDER_CLOUD_RUNPOD_RELAY_TOKEN` to the same relay token in its private
   service environment. Apply those settings to the backend, reaper and billing
   service. No provider key needs to be sent by EditorGPT in relay mode.
3. With those settings loaded, run this read-only smoke check on the server:

   ```sh
   python -c 'from app.render_cloud.provider import RunPod; from app.render_cloud.settings import CloudSettings; p=RunPod.from_settings(CloudSettings()); p.list(); p.close(); print("RunPod list succeeded")'
   ```

Keep cloud admission off until the storage, worker and measured-profile gates
in the rollout guide pass. A request without a relay token should return 401
and never reach RunPod. An authenticated relay can return an upstream 403;
successful deployment or a relay 401 alone does not prove RunPod access.

On a relay transport failure, the caller does not fall back to direct requests
or retry an uncertain create. Keep cleanup services on the same working
transport while unresolved Pods exist. Never put either token in URLs, source,
browser settings or logs. See [Vercel environment variables](https://vercel.com/docs/environment-variables).

The authenticated containment canary uses the RunPod v2 CPU catalog and
registry lookup before provisioning two vCPUs. The create path injects a
fixed containment-probe command and rejects caller-supplied environment
variables. The result endpoint returns only the probe boolean for a Pod
whose name matches the canary. Use a unique name and arm independent
deletion before sending the create request. After an uncertain create,
reconcile that name before considering another attempt.
