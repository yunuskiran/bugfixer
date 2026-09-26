# bugfixer

**AI Internal Support Agent** — an AI-powered Slack/Teams bot that diagnoses process failures by querying your log sources, extracting root causes with an LLM, linking related work items, and surfacing distributed trace context and error-frequency trends.

---

## Architecture

```
                         ┌──────────────────────────────────────────────────┐
  Slack (Socket Mode) ──▶│                                                  │
                         │            FastAPI (main.py)                     │
  Teams (Webhook)    ──▶│                                                  │
                         └────────────────────┬─────────────────────────────┘
                                              │
                                              ▼
                         ┌──────────────────────────────────────────────────┐
                         │                SupportAgent                      │
                         │                                                  │
                         │  1. Log Connectors  ←──── plugin registry        │
                         │     • Seq (CLEF HTTP)                            │
                         │     • Azure Application Insights (KQL)           │
                         │     • Grafana Loki (LogQL)                       │
                         │     • Sentry (Issues API)                        │
                         │     • Datadog (Logs v2)                          │
                         │     • File logs (plaintext + JSON-lines)         │
                         │           │ asyncio.gather                       │
                         │  2. OpenAI GPT-4o  →  root cause + fix + terms  │
                         │           │ asyncio.gather                       │
                         │  3. Issue Trackers  ←─── plugin registry         │
                         │     • Jira (JQL)                                 │
                         │     • Azure DevOps (WIQL)                        │
                         │     • Linear (GraphQL)                           │
                         │     • PagerDuty (Incidents API)                  │
                         │     • GitHub Issues (Search API)                 │
                         │           │                                      │
                         │  4. Enrichers  ←─────── plugin registry          │
                         │     • CorrelationEnricher (trace ID stitching)   │
                         │     • TrendEnricher (spike detection)            │
                         └──────────────────────────────────────────────────┘
```

---

## Plugin Architecture

Every log connector, issue tracker, and enricher is a **self-registering plugin**. Declaring `plugin_name="..."` in the class line is all that's needed:

```python
from src.connectors.base import BaseLogConnector, LogEntry

class MyConnector(BaseLogConnector, plugin_name="my_source"):
    @property
    def name(self) -> str:
        return "MySource"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        ...
```

The moment Python imports that module, the class is added to `BaseLogConnector._registry`. No changes to `core.py` are needed — just drop the file in `src/connectors/` and wire up the config key.

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
# Edit .env with your values — only OPENAI_API_KEY and bot tokens are required.
# Configure only the log sources and trackers you actually use.
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

### Required

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `SLACK_BOT_TOKEN` | Slack bot token (xoxb-…) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `SLACK_APP_TOKEN` | Slack Socket Mode token (xapp-…) |
| `TEAMS_APP_ID` | Microsoft Bot Framework app ID |
| `TEAMS_APP_PASSWORD` | Microsoft Bot Framework app password |

### Log Connectors (configure at least one)

| Variable | Description |
|---|---|
| `SEQ_URL` | Base URL of your Seq server (e.g. `http://seq:5341`) |
| `SEQ_API_KEY` | Seq API key (optional if auth disabled) |
| `AZURE_INSIGHTS_CONNECTION_STRING` | Application Insights connection string |
| `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` | Service principal (optional — falls back to DefaultAzureCredential) |
| `LOKI_URL` | Grafana Loki base URL (e.g. `http://loki:3100`) |
| `LOKI_USER` / `LOKI_PASSWORD` | Basic auth for Loki (optional) |
| `SENTRY_AUTH_TOKEN` | Sentry auth token |
| `SENTRY_ORG` | Sentry organization slug |
| `SENTRY_PROJECT` | Sentry project slug |
| `DATADOG_API_KEY` | Datadog API key |
| `DATADOG_APP_KEY` | Datadog Application key |
| `DATADOG_SITE` | Datadog site (default: `datadoghq.com`) |
| `FILE_LOG_PATHS` | Comma-separated file paths (plaintext or JSON-lines) |

### Issue Trackers (all optional)

| Variable | Description |
|---|---|
| `JIRA_URL` | Jira base URL |
| `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_PROJECT_KEY` | Jira credentials |
| `AZURE_DEVOPS_URL` / `AZURE_DEVOPS_PAT` / `AZURE_DEVOPS_PROJECT` | Azure DevOps credentials |
| `LINEAR_API_KEY` | Linear API key (`lin_api_…`) |
| `PAGERDUTY_API_KEY` | PagerDuty REST API v2 key |
| `GITHUB_TOKEN` | GitHub personal access token (`ghp_…`) |
| `GITHUB_REPOS` | Comma-separated `owner/repo` list to search |

### General

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Enrichers

After the LLM analysis, two enrichers run automatically in parallel:

### CorrelationEnricher 🔗
Scans log entries for distributed trace identifiers (`traceId`, `correlationId`, `requestId`, `spanId`), then re-queries all configured log sources with those IDs. This stitches together the full request path across microservices, showing you log lines from services you didn't even ask about.

### TrendEnricher 📈
Counts how many times the failing error appears in 15-minute, 1-hour, and 24-hour windows. If more than 20% of the 24h occurrences happened in the last 15 minutes, it surfaces a **⚠️ SPIKE DETECTED** alert so the team knows whether this is a new fire or a slow burn.

---

## Example Interactions

### Slack
```
@bugfixer Why did the payment service fail at 3am?

🔍 Analyzing your question, please wait...

*🔍 Analysis for:* Why did the payment service fail at 3am?

*Root Cause*
NullPointerException in PaymentService.process at line 42 due to
an uninitialized payment gateway client after a DI failure on startup.

*Suggested Fix*
1. Initialize the payment gateway client eagerly in the constructor
2. Add a health check that validates the client before serving requests
3. Add circuit-breaker around gateway calls

*Log Sources Queried:* Seq, Loki, Sentry
*Log Entries Found:* 23

*Related Work Items*
• <https://linear.app/myteam/issue/ENG-42|[ENG-42] NPE in PaymentService> — In Progress
• <https://github.com/myorg/backend/issues/99|[#99] Null client after pod restart> — open

*🔗 Correlation Analysis*
Found 2 correlation ID(s): abc123def456, ff00ff00abcd.
Re-queried connectors and found 8 additional log entries linked to these IDs.

*📈 Trend Analysis*
Error frequency — last 15min: 18, last 1h: 21, last 24h: 24.
⚠️ SPIKE DETECTED: 75% of 24h occurrences happened in the last 15 minutes.
```

### Teams
The Teams bot sends an Adaptive Card with the same information formatted for the Teams UI, including enrichment sections at the bottom.

---

## How to Write a Custom Plugin

### Custom log connector (3 steps)

1. Create `src/connectors/my_source.py`:

```python
from .base import BaseLogConnector, LogEntry

class MySourceConnector(BaseLogConnector, plugin_name="my_source"):
    def __init__(self, url: str) -> None:
        self._url = url

    @property
    def name(self) -> str:
        return "MySource"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        # Query your source, return LogEntry objects
        ...
```

2. Add config fields to `src/config.py` (Pydantic Settings) and add the module path to `BUILTIN_CONNECTOR_MODULES` in `src/plugins/registry.py`.

3. Add instantiation logic to `SupportAgent._build_connectors()`.

### Custom enricher

```python
from src.enrichers.base import BaseEnricher, Enrichment

class MyEnricher(BaseEnricher, plugin_name="my_enricher"):
    async def enrich(self, result, question, connectors) -> Enrichment:
        # Post-process the AnalysisResult and return an Enrichment
        return Enrichment(name="my_enricher", summary="...", data={...})
```

Add it to `SupportAgent._build_enrichers()` and it will run automatically after every analysis.

---

## License

MIT

