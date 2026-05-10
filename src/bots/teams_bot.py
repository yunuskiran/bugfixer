from __future__ import annotations
import logging
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes
from ..agent.core import SupportAgent

logger = logging.getLogger(__name__)


class BugFixerTeamsBot(ActivityHandler):
    def __init__(self, agent: SupportAgent) -> None:
        super().__init__()
        self._agent = agent

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            return

        # Send typing indicator
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        try:
            result = await self._agent.analyze(text)
            card = self._agent.format_teams_card(result, text)
            reply = Activity(
                type=ActivityTypes.message,
                attachments=[
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card,
                    }
                ],
            )
        except Exception as exc:
            logger.error("Agent analysis failed for Teams: %s", exc)
            reply = Activity(
                type=ActivityTypes.message,
                text=f"❌ Sorry, I encountered an error while analyzing your request: {exc}",
            )

        await turn_context.send_activity(reply)

    async def on_members_added_activity(self, members_added, turn_context: TurnContext) -> None:
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 Hello! I'm BugFixer, your AI support agent. "
                    "Ask me *'Why did this process fail?'* and I'll analyze logs and suggest fixes."
                )
