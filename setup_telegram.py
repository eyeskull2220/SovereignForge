#!/usr/bin/env python3
"""Interactive Telegram bot setup for SovereignForge."""

import os
import sys


def main():
    print("SovereignForge Telegram Alert Setup")
    print("=" * 40)
    print()
    print("1. Message @BotFather on Telegram")
    print("2. Send /newbot and follow prompts")
    print("3. Copy the bot token")
    print()

    token = input("Paste your bot token: ").strip()
    if not token:
        print("No token provided. Exiting.")
        sys.exit(1)

    print()
    print("4. Start a chat with your new bot")
    print("5. Send any message to it")
    print(f"6. Visit: https://api.telegram.org/bot{token}/getUpdates")
    print()

    chat_id = input("Paste your chat ID: ").strip()
    if not chat_id:
        print("No chat ID provided. Exiting.")
        sys.exit(1)

    # Write to .env
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            env_lines = f.readlines()

    # Update or add vars
    updated = set()
    new_lines = []
    for line in env_lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
            updated.add("token")
        elif line.startswith("TELEGRAM_CHAT_IDS="):
            new_lines.append(f"TELEGRAM_CHAT_IDS={chat_id}\n")
            updated.add("chat")
        elif line.startswith("TELEGRAM_ENABLED="):
            new_lines.append("TELEGRAM_ENABLED=true\n")
            updated.add("enabled")
        else:
            new_lines.append(line)

    if "token" not in updated:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
    if "chat" not in updated:
        new_lines.append(f"TELEGRAM_CHAT_IDS={chat_id}\n")
    if "enabled" not in updated:
        new_lines.append("TELEGRAM_ENABLED=true\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\nSaved to {env_path}")
    print()
    print("To test, run:")
    print('  python -c "import asyncio; import sys; sys.path.insert(0, \'src\'); '
          'from telegram_alerts import send_test_alert; print(asyncio.run(send_test_alert()))"')


if __name__ == "__main__":
    main()
