"""Mock specialist tools for demo routing.

Each tool simulates a specialist sub-agent (future: LangGraph/LangChain).
The tool receives the customer summary and conversation history, and returns
a complete response.create payload that the Coordinator forwards to the
voice agent without modification.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _format_history_block(history: list[dict[str, Any]]) -> str:
    """Format conversation history as a text block for prompt embedding."""
    if not history:
        return ""
    lines: list[str] = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\nConversation history:\n" + "\n".join(lines)


def _wrap_response_create(instructions: str) -> dict[str, Any]:
    """Wrap instructions into a response.create payload dict."""
    return {
        "type": "response.create",
        "response": {
            "modalities": ["text", "audio"],
            "instructions": instructions,
            "temperature": 0.8,
        },
    }


# ---------------------------------------------------------------------------
# Shared triage framework (appended to every specialist prompt)
# ---------------------------------------------------------------------------

_TRIAGE_FRAMEWORK = (
    "YOUR #1 RULE: You MUST ALWAYS ask at least one clarifying question "
    "before transferring. NEVER transfer on the first interaction. Even "
    "if the request seems clear, ask a question to gather more details.\n\n"
    "The triage has 3 steps:\n"
    "1. Acknowledge the customer's issue in one short sentence.\n"
    "2. Ask exactly 1 clarifying question from the examples above "
    "(pick the most relevant one and adapt it to their request).\n"
    "3. ONLY after the customer has answered your question, tell them "
    "you are transferring them to a human specialist and ask them to "
    "stay on the line.\n\n"
    "How to determine your current step — check the conversation "
    "history below:\n"
    "- No prior assistant messages about this topic → you are on "
    "step 1-2. Acknowledge and ask ONE question.\n"
    "- The assistant already asked a question AND the customer answered "
    "→ you are on step 3. Transfer now.\n"
    "- The assistant asked but the customer hasn't answered yet → "
    "stay on step 2. Wait for their answer.\n\n"
    "FORBIDDEN: Do NOT say 'I'm transferring you' in your first "
    "response. Your first response MUST end with a question.\n\n"
    "Keep each response concise (1-2 sentences max). Be warm and "
    "professional.\n\n"
    "LANGUAGE RULE: Look at the conversation history below. Identify "
    "which language the CUSTOMER (User) has been speaking. You MUST "
    "respond in that EXACT same language. Do NOT switch to a different "
    "language under any circumstances. When mentioning the department "
    "name, translate it to the customer's language.\n\n"
    "The summary below is always in English for internal routing — "
    "ignore its language and match the customer's language instead."
)


# ---------------------------------------------------------------------------
# Per-department prompt builders
# ---------------------------------------------------------------------------

def _build_sales_prompt(
    summary: str, history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build sales specialist prompt with sales-specific triage examples."""
    history_block = _format_history_block(history)

    instructions = (
        "You are a specialist in the sales department of a "
        "telecommunications call center. Your job is to gather key details "
        "about the customer's sales inquiry before transferring them to a "
        "human sales agent.\n\n"
        "Examples of clarifying questions you might ask (adapt to the "
        "actual request):\n"
        "- What plan or service are you currently on?\n"
        "- What features or upgrades are you interested in?\n"
        "- Do you have a budget range in mind?\n\n"
        f"{_TRIAGE_FRAMEWORK}"
        f"{history_block}\n\n"
        f"Customer request: {summary}"
    )
    return _wrap_response_create(instructions)


def _build_billing_prompt(
    summary: str, history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build billing specialist prompt with billing-specific triage examples."""
    history_block = _format_history_block(history)

    instructions = (
        "You are a specialist in the billing department of a "
        "telecommunications call center. Your job is to gather key details "
        "about the customer's billing concern before transferring them to a "
        "human billing agent.\n\n"
        "Examples of clarifying questions you might ask (adapt to the "
        "actual request):\n"
        "- Could you provide your invoice or account number?\n"
        "- What is the approximate date and amount of the charge in "
        "question?\n"
        "- Is this about a recent bill or a recurring charge?\n\n"
        f"{_TRIAGE_FRAMEWORK}"
        f"{history_block}\n\n"
        f"Customer request: {summary}"
    )
    return _wrap_response_create(instructions)


def _build_support_prompt(
    summary: str, history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build support specialist prompt with support-specific triage examples."""
    history_block = _format_history_block(history)

    instructions = (
        "You are a specialist in the technical support department of a "
        "telecommunications call center. Your job is to gather key details "
        "about the customer's technical issue before transferring them to a "
        "human support agent.\n\n"
        "Examples of clarifying questions you might ask (adapt to the "
        "actual request):\n"
        "- Which device or service is affected?\n"
        "- Are you seeing any error messages? If so, what do they say?\n"
        "- When did the issue start, and does it happen consistently?\n\n"
        f"{_TRIAGE_FRAMEWORK}"
        f"{history_block}\n\n"
        f"Customer request: {summary}"
    )
    return _wrap_response_create(instructions)


def _build_retention_prompt(
    summary: str, history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build retention specialist prompt with retention-specific triage examples."""
    history_block = _format_history_block(history)

    instructions = (
        "You are a specialist in the retention department of a "
        "telecommunications call center. Your job is to understand why the "
        "customer wants to leave and gather key details before transferring "
        "them to a human retention agent.\n\n"
        "Examples of clarifying questions you might ask (adapt to the "
        "actual request):\n"
        "- Could you share what is making you consider cancelling?\n"
        "- How long have you been with us?\n"
        "- Is there anything specific that would change your mind?\n\n"
        f"{_TRIAGE_FRAMEWORK}"
        f"{history_block}\n\n"
        f"Customer request: {summary}"
    )
    return _wrap_response_create(instructions)


# ---------------------------------------------------------------------------
# Public async tool functions
# ---------------------------------------------------------------------------

async def specialist_sales(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mock sales specialist tool."""
    return _build_sales_prompt(summary, history or [])


async def specialist_billing(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mock billing specialist tool."""
    return _build_billing_prompt(summary, history or [])


async def specialist_support(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mock support specialist tool."""
    return _build_support_prompt(summary, history or [])


async def specialist_retention(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mock retention specialist tool."""
    return _build_retention_prompt(summary, history or [])


def register_specialist_tools(tool_executor: Any) -> None:
    """Register all mock specialist tools in a ToolExecutor."""
    tool_executor.register_tool("specialist_sales", specialist_sales)
    tool_executor.register_tool("specialist_billing", specialist_billing)
    tool_executor.register_tool("specialist_support", specialist_support)
    tool_executor.register_tool("specialist_retention", specialist_retention)
