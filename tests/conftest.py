from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from src.connectors.base import LogEntry
from src.trackers.base import WorkItem


@pytest.fixture
def sample_log_entries() -> list[LogEntry]:
    return [
        LogEntry(
            timestamp=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            level="ERROR",
            message="NullPointerException in PaymentService.process at line 42",
            source="Seq",
            properties={"thread": "main", "service": "payment"},
        ),
        LogEntry(
            timestamp=datetime(2024, 6, 1, 11, 59, 50, tzinfo=timezone.utc),
            level="WARN",
            message="Database connection pool exhausted, retrying...",
            source="FileLog:/var/log/app.log",
            properties={"pool_size": 10, "waiting": 25},
        ),
        LogEntry(
            timestamp=datetime(2024, 6, 1, 11, 59, 40, tzinfo=timezone.utc),
            level="INFO",
            message="Payment request received for order 9981",
            source="AzureInsights",
            properties={"order_id": "9981"},
        ),
    ]


@pytest.fixture
def sample_work_items() -> list[WorkItem]:
    return [
        WorkItem(
            id="PROJ-123",
            title="NullPointerException in PaymentService",
            url="https://jira.example.com/browse/PROJ-123",
            status="Open",
            item_type="Bug",
        ),
        WorkItem(
            id="PROJ-456",
            title="DB connection pool exhaustion under load",
            url="https://jira.example.com/browse/PROJ-456",
            status="In Progress",
            item_type="Story",
        ),
    ]


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.openai_api_key = "sk-test-key"
    settings.slack_bot_token = "xoxb-test"
    settings.slack_signing_secret = "test-secret"
    settings.slack_app_token = "xapp-test"
    settings.teams_app_id = "teams-app-id"
    settings.teams_app_password = "teams-app-password"
    settings.seq_url = None
    settings.seq_api_key = None
    settings.azure_insights_connection_string = None
    settings.azure_tenant_id = None
    settings.azure_client_id = None
    settings.azure_client_secret = None
    settings.file_log_paths = None
    settings.file_log_paths_list = []
    settings.jira_url = None
    settings.jira_email = None
    settings.jira_api_token = None
    settings.jira_project_key = None
    settings.azure_devops_url = None
    settings.azure_devops_pat = None
    settings.azure_devops_project = None
    settings.log_level = "INFO"
    return settings


@pytest.fixture
def mock_openai_response() -> MagicMock:
    choice = MagicMock()
    choice.message.content = (
        "1. Root Cause: NullPointerException in PaymentService.process at line 42 "
        "due to uninitialized payment gateway client.\n"
        "2. Contributing Factors: Database connection pool was exhausted prior to the failure, "
        "causing timeout and null return.\n"
        "3. Suggested Fix: Initialize the payment gateway client in the constructor and add "
        "connection pool monitoring with alerting.\n"
        "4. Search Terms: NullPointerException, PaymentService, connection pool, payment gateway"
    )
    response = MagicMock()
    response.choices = [choice]
    return response
