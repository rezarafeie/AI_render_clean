# EditorGPT Telegram Studio

The private bot links to the existing account through the app's confirmation
page. Questions get an in-place Gateway response via Redis without creating
a Studio conversation. An explicit work request (or the Studio button below a
quick reply) goes to Studio. An uncaptioned file stays pending until the person
provides instructions. The engine picker uses the same Lite/Medium/Pro account
preference as web Settings.

InstaGPT opens the existing /insta Mini App. The Hermes button selects a native
Telegram conversation using the existing Hermes chat service on the private
Compose network (hermes:8001), authenticated as the connected account. External
connections and full account management are available through Settings.

Studio flow reuses persisted projects and approval callbacks. The bot mirrors
assistant text, progress, finished motion albums, available narration and
outputs. Media above the Bot API delivery threshold is opened through Studio.

Configure a dedicated bot in BotFather and set these server-side values:

- `EDITOR_TELEGRAM_BOT_TOKEN`: dedicated bot token.
- `EDITOR_TELEGRAM_WEBHOOK_SECRET`: independent random value permitted by Telegram's webhook secret format.
- `EDITOR_TELEGRAM_STUDIO_URL`: HTTPS origin serving both the web app and the API.
- `REDIS_URL`: existing Redis. Use persistence and an eviction policy that keeps account links.

Deploy backend and frontend together. Register the bot webhook with Telegram's `setWebhook` using the URL `<origin>/api/integrations/telegram/webhook`, the configured `secret_token` and `allowed_updates: ["message", "callback_query"]`. Avoid printing the bot token in logs or CLI output.

Smoke-test linking, quick chat without a Studio entry, a file followed by a
request, engine preference across Telegram and web, and the Hermes button.
Use the account connection page to revoke a linked Telegram account.

## Dedicated Telegram relay

Deploy `deploy/editor-telegram-relay` to a separate Vercel project. Set
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` and a fresh
`RELAY_SECRET` as server-side secrets. Use the EditorGPT bot token. The developer
API ID and hash may be shared with the existing integration, while the bot
authorization and relay secret are specific to EditorGPT.

On EditorGPT, set `EDITOR_TELEGRAM_RELAY_SECRET` to the same relay secret.
Point `EDITOR_TELEGRAM_BOT_RELAY_URL` at the deployed `/api/bot` and
`EDITOR_TELEGRAM_DOWNLOAD_RELAY_URL` at `/api/download`. Register the webhook
for both `message` and `callback_query` updates. Probe getMe and test a fresh
video greater than 20 MiB in the linked account. The relay currently handles
JSON Bot API calls and authenticated MTProto downloads. Direct multipart
audio and output delivery require connectivity to Telegram's Bot API.
