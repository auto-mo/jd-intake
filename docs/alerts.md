# Alerts (optional)

jd-intake can send you a Telegram message when something breaks and will keep failing until you
act: Claude's login expired or hit a usage limit, the inbox could not be read several times in a
row, an approved email could not be sent, an evaluation or build failed. It sends failures only, never routine news, and at
most one message per problem per hour.

It matters most when the server runs on another machine ([server-mode.md](server-mode.md)),
where you would not otherwise see an error.

## Set it up

1. In Telegram, open a chat with **@BotFather**, send `/newbot`, and follow the prompts. It
   gives you a bot token.
2. Send any message to your new bot, then open
   `https://api.telegram.org/bot<token>/getUpdates` in a browser. The number at
   `"chat":{"id": ...}` is your chat id.
3. Save both to `.env` at the repo root with hidden input:

   ```bash
   scripts/set_secret.sh TELEGRAM_BOT_TOKEN
   ```

   and the same command with `TELEGRAM_CHAT_ID`.
4. Set `features: alerts: true` in `profile/profile.yaml` and restart the server.

Messages contain a short description of the failure, with the company and role when it is about a job.
They never contain your profile or the content of your mail.
