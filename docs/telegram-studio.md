# EditorGPT Telegram Studio

The first integration supports private chat, account linking, text and link submissions, Instagram reference intent, Lite/Medium commands, and opening the same Studio project in a Telegram Mini App. Users approve renders and access media in Studio.

Configure a dedicated bot in BotFather and set these server-side values:

- `EDITOR_TELEGRAM_BOT_TOKEN`: dedicated bot token.
- `EDITOR_TELEGRAM_WEBHOOK_SECRET`: independent random value permitted by Telegram's webhook secret format.
- `EDITOR_TELEGRAM_STUDIO_URL`: HTTPS origin serving both the web app and the API.
- `REDIS_URL`: existing Redis. Use persistence and an eviction policy that keeps account links.

Deploy backend and frontend together. Register the bot webhook with Telegram's `setWebhook` using the URL `<origin>/api/integrations/telegram/webhook`, the configured `secret_token` and `allowed_updates: ["message"]`. Avoid printing the bot token in logs or CLI output.

Validate `/start`, link using the existing web login, send a link, try `/status`, open the conversation inside Telegram, and revoke the account at `/telegram/link`. Bot-native confirmation, live push, and large Telegram media transfer remain separate work.

The bot also offers EditorGPT, InstaGPT, Projects, Library and Settings Mini App entry points. Use `/updates` for persisted Studio activity, assistant replies and available status audio. Use `/output` for the current completed output. With Telegram's hosted API, direct input is capped at 20 MiB and direct output at 50 MB. Larger media uses Studio's upload and preview. The bot currently fetches updates on command, while the Mini App continues to use Studio's live feed.
