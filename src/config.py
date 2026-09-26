from __future__ import annotations
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # Slack
    slack_bot_token: str = Field(..., alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field(..., alias="SLACK_SIGNING_SECRET")
    slack_app_token: str = Field(..., alias="SLACK_APP_TOKEN")

    # Teams
    teams_app_id: str = Field(..., alias="TEAMS_APP_ID")
    teams_app_password: str = Field(..., alias="TEAMS_APP_PASSWORD")

    # Seq
    seq_url: Optional[str] = Field(None, alias="SEQ_URL")
    seq_api_key: Optional[str] = Field(None, alias="SEQ_API_KEY")

    # Azure Application Insights
    azure_insights_connection_string: Optional[str] = Field(None, alias="AZURE_INSIGHTS_CONNECTION_STRING")
    azure_tenant_id: Optional[str] = Field(None, alias="AZURE_TENANT_ID")
    azure_client_id: Optional[str] = Field(None, alias="AZURE_CLIENT_ID")
    azure_client_secret: Optional[str] = Field(None, alias="AZURE_CLIENT_SECRET")

    # File logs — comma-separated list of absolute or relative paths
    file_log_paths: Optional[str] = Field(None, alias="FILE_LOG_PATHS")

    # Jira
    jira_url: Optional[str] = Field(None, alias="JIRA_URL")
    jira_email: Optional[str] = Field(None, alias="JIRA_EMAIL")
    jira_api_token: Optional[str] = Field(None, alias="JIRA_API_TOKEN")
    jira_project_key: Optional[str] = Field(None, alias="JIRA_PROJECT_KEY")

    # Azure DevOps
    azure_devops_url: Optional[str] = Field(None, alias="AZURE_DEVOPS_URL")
    azure_devops_pat: Optional[str] = Field(None, alias="AZURE_DEVOPS_PAT")
    azure_devops_project: Optional[str] = Field(None, alias="AZURE_DEVOPS_PROJECT")

    # Grafana Loki
    loki_url: Optional[str] = Field(None, alias="LOKI_URL")
    loki_user: Optional[str] = Field(None, alias="LOKI_USER")
    loki_password: Optional[str] = Field(None, alias="LOKI_PASSWORD")

    # Sentry
    sentry_auth_token: Optional[str] = Field(None, alias="SENTRY_AUTH_TOKEN")
    sentry_org: Optional[str] = Field(None, alias="SENTRY_ORG")
    sentry_project: Optional[str] = Field(None, alias="SENTRY_PROJECT")

    # Datadog
    datadog_api_key: Optional[str] = Field(None, alias="DATADOG_API_KEY")
    datadog_app_key: Optional[str] = Field(None, alias="DATADOG_APP_KEY")
    datadog_site: str = Field("datadoghq.com", alias="DATADOG_SITE")

    # Linear
    linear_api_key: Optional[str] = Field(None, alias="LINEAR_API_KEY")

    # PagerDuty
    pagerduty_api_key: Optional[str] = Field(None, alias="PAGERDUTY_API_KEY")

    # GitHub Issues
    github_token: Optional[str] = Field(None, alias="GITHUB_TOKEN")
    github_repos: Optional[str] = Field(None, alias="GITHUB_REPOS")

    # General
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @property
    def file_log_paths_list(self) -> list[str]:
        if not self.file_log_paths:
            return []
        return [p.strip() for p in self.file_log_paths.split(",") if p.strip()]

    @property
    def github_repos_list(self) -> list[str]:
        if not self.github_repos:
            return []
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]
