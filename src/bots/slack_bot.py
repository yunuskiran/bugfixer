from __future__ import annotations
import logging
import re
from slack_bolt.async_app import AsyncApp
from ..agent.core import SupportAgent

logger = logging.getLogger(__name__)


def create_slack_app(agent: SupportAgent, bot_token: str, signing_secret: str) -> AsyncApp:
    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    async def handle_question(text: str, say, client, channel: str, ts: str | None = None) -> None:
        # Post a "thinking" message
        thinking = await say("🔍 Analyzing your question, please wait...")
        thinking_ts = thinking.get("ts")

        try:
            result = await agent.analyze(text)
            message = agent.format_slack_message(result, text)
        except Exception as exc:
            logger.error("Agent analysis failed: %s", exc)
            message = f"❌ Sorry, I encountered an error while analyzing: {exc}"

        # Update the thinking message with the real response
        try:
            if thinking_ts:
                await client.chat_update(channel=channel, ts=thinking_ts, text=message)
            else:
                await say(message)
        except Exception as exc:
            logger.error("Failed to update Slack message: %s", exc)
            await say(message)

    @app.event("app_mention")
    async def handle_mention(event: dict, say, client) -> None:
        text = event.get("text", "")
        # Strip the bot mention (@BotName)
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
        channel = event.get("channel", "")
        ts = event.get("ts")
        await handle_question(text, say, client, channel, ts)

    @app.event("message")
    async def handle_dm(event: dict, say, client) -> None:
        # Only respond to DMs (channel_type == "im") and ignore bot messages
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id"):
            return
        text = event.get("text", "").strip()
        if not text:
            return
        channel = event.get("channel", "")
        ts = event.get("ts")
        await handle_question(text, say, client, channel, ts)

    return app


async def start_socket_mode(app: AsyncApp, app_token: str) -> None:
    handler = AsyncSocketModeHandler(app, app_token)
    await handler.start_async()
