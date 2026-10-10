#!/usr/bin/env bash
# Store one secret in .env without it appearing on screen, in your shell history or in a chat.
# Usage: scripts/set_secret.sh KEY_NAME      (for example: scripts/set_secret.sh APIFY_TOKEN)
set -euo pipefail
key="${1:?usage: scripts/set_secret.sh KEY_NAME}"
case "$key" in *[!A-Z0-9_]*) echo "Key names are capital letters, digits and underscores." >&2; exit 1;; esac
env_file="$(cd "$(dirname "$0")/.." && pwd)/.env"
umask 077
read -rsp "Paste $key, then press Enter: " value; echo
[ -n "$value" ] || { echo "Nothing pasted; nothing saved."; exit 1; }
touch "$env_file"
{ grep -v "^${key}=" "$env_file" || true; printf '%s=%s\n' "$key" "$value"; } > "$env_file.tmp"
mv "$env_file.tmp" "$env_file"; chmod 600 "$env_file"
echo "Saved $key (${#value} characters) to .env"
