from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity

from .config import Settings
from .agent.core import SupportAgent
from .bots.slack_bot import create_slack_app
from .bots.teams_bot import BugFixerTeamsBot

logger = logging.getLogger(__name__)

# Module-level singletons
_agent: SupportAgent | None = None
_teams_adapter: BotFrameworkAdapter | None = None
_teams_bot: BugFixerTeamsBot | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _agent, _teams_adapter, _teams_bot

    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level)
    logger.info("Starting BugFixer support agent…")

    _agent = SupportAgent(settings)

    # Teams adapter
    adapter_settings = BotFrameworkAdapterSettings(
        app_id=settings.teams_app_id,
        app_password=settings.teams_app_password,
    )
    _teams_adapter = BotFrameworkAdapter(adapter_settings)
    _teams_bot = BugFixerTeamsBot(_agent)

    # Slack — run in Socket Mode as a background task
    import asyncio
    slack_app = create_slack_app(
        agent=_agent,
        bot_token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )

    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    slack_handler = AsyncSocketModeHandler(slack_app, settings.slack_app_token)
    slack_task = asyncio.create_task(slack_handler.start_async())
    logger.info("Slack Socket Mode started")

    yield

    # Cleanup
    slack_task.cancel()
    try:
        await slack_task
    except asyncio.CancelledError:
        pass
    logger.info("BugFixer shut down")


app = FastAPI(title="BugFixer AI Support Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "bugfixer"}


@app.post("/teams/messages")
async def teams_messages(request: Request) -> Response:
    if _teams_adapter is None or _teams_bot is None:
        return Response(content="Service not ready", status_code=503)

    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def call_agent(turn_context):
        await _teams_bot.on_turn(turn_context)

    await _teams_adapter.process_activity(activity, auth_header, call_agent)
    return Response(status_code=200)
