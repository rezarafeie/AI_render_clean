# Composio relay (Vercel)

The EditorGPT server reaches `backend.composio.dev` slowly and sometimes not at all (Hermes logs `APIConnectionError`). This relay lets Hermes call
Composio through Vercel. It stores **no Composio key**: Hermes sends its own `x-api-key`, the relay only passes it on. `RELAY_SECRET` (a Vercel
environment variable) must accompany every call. Only `api/v3/*` of `backend.composio.dev` is forwarded.

Deploy (your Vercel account, project name e.g. `rafiei-composio-relay`):

    cd deploy/composio-relay
    vercel link
    vercel env add RELAY_SECRET production      # paste a long random value
    vercel deploy --prod

Server `.env` (the same random value):

    COMPOSIO_BASE_URL=https://<project>.vercel.app/api/composio
    COMPOSIO_RELAY_SECRET=<the same value>

then recreate the `hermes` container. Remove `COMPOSIO_BASE_URL` to go back to the direct connection. Tests: `node --test relay.test.mjs`.
