# bugfixer

**AI Internal Support Agent** — an AI-powered Slack/Teams bot that diagnoses process failures by querying your log sources, extracting root causes with an LLM, and linking related work items from Jira or Azure DevOps.

---

## Architecture

```
                         ┌──────────────────────────────────┐
  Slack (Socket Mode) ──▶│                                  │
                         │         FastAPI (main.py)        │
  Teams (Webhook)    ──▶│                                  │
                         └──────────────┬───────────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────────┐
                         │         SupportAgent             │
                         │  ┌────────────────────────────┐  │
                         │  │    Log Connectors (async)  │  │
                         │  │  • SeqConnector            │  │
                         │  │  • AzureInsightsConnector  │  │
                         │  │  • FileLogConnector        │  │
                         │  └────────────┬───────────────┘  │
                         │               │ log entries       │
                         │  ┌────────────▼───────────────┐  │
                         │  │   OpenAI GPT-4o            │  │
                         │  │   Root Cause + Fix + Terms │  │
                         │  └────────────┬───────────────┘  │
                         │               │ search terms      │
                         │  ┌────────────▼───────────────┐  │
                         │  │    Work Item Trackers      │  │
                         │  │  • JiraTracker             │  │
                         │  │  • AzureDevOpsTracker      │  │
                         │  └────────────────────────────┘  │
                         └──────────────────────────────────┘
```

---

## Setup

### Prerequisites
- Python ≥ 3.11
- A Slack app with Socket Mode enabled and the following bot scopes:
  `app_mentions:read`, `chat:write`, `im:history`, `im:read`
- A Microsoft Bot Framework registration (for Teams)
- OpenAI API key

### 1. Clone and install

```bash
git clone https://github.com/yourorg/bugfixer.git
cd bugfixer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Or with Docker Compose:

```bash
docker-compose up -d
```

### 4. Run tests

```bash
pytest
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `SLACK_BOT_TOKEN` | ✅ | Slack bot token (xoxb-…) |
| `SLACK_SIGNING_SECRET` | ✅ | Slack app signing secret |
| `SLACK_APP_TOKEN` | ✅ | Slack Socket Mode token (xapp-…) |
| `TEAMS_APP_ID` | ✅ | Microsoft Bot Framework app ID |
| `TEAMS_APP_PASSWORD` | ✅ | Microsoft Bot Framework app password |
| `SEQ_URL` | ☑️ | Base URL of your Seq server |
| `SEQ_API_KEY` | ☑️ | Seq API key (if auth enabled) |
| `AZURE_INSIGHTS_CONNECTION_STRING` | ☑️ | Application Insights connection string |
| `AZURE_TENANT_ID` | ☑️ | Azure tenant ID (for service principal auth) |
| `AZURE_CLIENT_ID` | ☑️ | Azure client ID |
| `AZURE_CLIENT_SECRET` | ☑️ | Azure client secret |
| `FILE_LOG_PATHS` | ☑️ | Comma-separated list of log file paths |
| `JIRA_URL` | ☑️ | Jira base URL |
| `JIRA_EMAIL` | ☑️ | Jira user email |
| `JIRA_API_TOKEN` | ☑️ | Jira API token |
| `JIRA_PROJECT_KEY` | ☑️ | Jira project key (e.g. `PROJ`) |
| `AZURE_DEVOPS_URL` | ☑️ | Azure DevOps org URL |
| `AZURE_DEVOPS_PAT` | ☑️ | Azure DevOps personal access token |
| `AZURE_DEVOPS_PROJECT` | ☑️ | Azure DevOps project name |
| `LOG_LEVEL` | ☑️ | Logging level (default: `INFO`) |

✅ Required · ☑️ Optional (at least one log source must be configured)

---

## Example Interactions

### Slack
```
@bugfixer Why did the payment service fail at 3am?

🔍 Analyzing your question, please wait...

*🔍 Analysis for:* Why did the payment service fail at 3am?

*Root Cause*
NullPointerException in PaymentService.process at line 42 due to
an uninitialized payment gateway client after a dependency injection
failure during startup.

*Suggested Fix*
1. Initialize the payment gateway client eagerly in the constructor
2. Add a health check that validates the client is non-null before serving requests
3. Add circuit-breaker around gateway calls

*Log Sources Queried:* Seq, FileLog
*Log Entries Found:* 14

*Related Work Items*
• <https://jira.example.com/browse/PROJ-123|[PROJ-123] NPE in PaymentService gateway init> — Open
• <https://jira.example.com/browse/PROJ-456|[PROJ-456] Null client after pod restart> — In Progress
```

### Teams
The Teams bot sends an Adaptive Card with the same information formatted for the Teams UI.

---

## How to Add a New Log Connector

1. Create `src/connectors/my_source.py`:

```python
from .base import BaseLogConnector, LogEntry

class MySourceConnector(BaseLogConnector):
    def __init__(self, url: str) -> None:
        self._url = url

    @property
    def name(self) -> str:
        return "MySource"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        # Query your log source and return LogEntry objects
        ...
```

2. Add your connector's config fields to `src/config.py` (Pydantic Settings).

3. Register it in `SupportAgent._build_connectors()` in `src/agent/core.py`:

```python
if settings.my_source_url:
    connectors.append(MySourceConnector(url=settings.my_source_url))
```

4. Add tests in `tests/test_connectors.py`.

That's it — the agent will automatically query your new source in parallel with the others.

---

## License

MIT