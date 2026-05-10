ROOT_CAUSE_PROMPT = """You are an expert software engineer and site reliability engineer.
Analyze the following log entries and identify the root cause of the failure.

User question: {question}

Log entries from {sources}:
{log_entries}

Provide:
1. Root Cause: A clear, concise explanation of what went wrong
2. Contributing Factors: Any secondary issues
3. Suggested Fix: Concrete steps to resolve the issue
4. Search Terms: 3-5 keywords to find related work items (comma-separated)

Be specific. Reference log messages and timestamps in your analysis."""

ISSUE_SEARCH_PROMPT = """Based on this root cause analysis, suggest search terms for finding related work items:

Root cause: {root_cause}
Error keywords: {error_keywords}

Return only a comma-separated list of 3-5 search terms."""
