"""Specialist tools for triage routing.

Each tool generates a triage response by calling a text model (gpt-4o) with
the department prompt and conversation history. The text model follows
structured triage instructions reliably. If the text model call fails,
the tool falls back to returning a response.create dict for the Realtime
model to interpret (legacy behavior).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Module-level client (configured at startup)
# ---------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None
_model: str = "gpt-4o"
_timeout_s: float = 5.0


def configure(api_key: str, model: str, timeout_s: float) -> None:
    """Initialize the shared httpx client for text model calls."""
    global _client, _model, _timeout_s
    _model = model
    _timeout_s = timeout_s
    _client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(timeout_s),
    )


async def close() -> None:
    """Shut down the shared httpx client gracefully."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Text model call
# ---------------------------------------------------------------------------

async def _call_text_model(system_prompt: str, user_message: str) -> str | None:
    """Call the text model and return the response text, or None on failure."""
    if _client is None:
        logger.warning("specialist_text_model_not_configured")
        return None

    try:
        resp = await _client.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": _model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 200,
                "temperature": 0.8,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            logger.warning("specialist_text_model_empty_response")
            return None
        return content.strip()
    except httpx.TimeoutException:
        logger.warning("specialist_text_model_timeout", timeout_s=_timeout_s)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "specialist_text_model_http_error",
            status_code=exc.response.status_code,
        )
        return None
    except Exception:
        logger.warning("specialist_text_model_error", exc_info=True)
        return None


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
# Per-department system prompts
# ---------------------------------------------------------------------------

_SALES_SYSTEM_PROMPT = (
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
)

_BILLING_SYSTEM_PROMPT = (
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
)

_SUPPORT_SYSTEM_PROMPT = (
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
)

_RETENTION_SYSTEM_PROMPT = (
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
)

_DEPARTMENT_SYSTEM_PROMPTS: dict[str, str] = {
    "sales": _SALES_SYSTEM_PROMPT,
    "billing": _BILLING_SYSTEM_PROMPT,
    "support": _SUPPORT_SYSTEM_PROMPT,
    "retention": _RETENTION_SYSTEM_PROMPT,
}


# ---------------------------------------------------------------------------
# Specialist call (text model with fallback)
# ---------------------------------------------------------------------------

async def _run_specialist(
    department: str,
    summary: str,
    history: list[dict[str, Any]],
) -> str | dict[str, Any]:
    """Call text model for triage response; fall back to response.create dict."""
    system_prompt = _DEPARTMENT_SYSTEM_PROMPTS[department]
    history_block = _format_history_block(history)
    user_message = f"{history_block}\n\nCustomer request: {summary}"

    text = await _call_text_model(system_prompt, user_message)
    if text is not None:
        return text

    # Fallback: build full instructions for Realtime model to interpret
    logger.warning("specialist_fallback_to_realtime", department=department)
    full_instructions = f"{system_prompt}{history_block}\n\nCustomer request: {summary}"
    return _wrap_response_create(full_instructions)


# ---------------------------------------------------------------------------
# Public async tool functions
# ---------------------------------------------------------------------------

async def specialist_sales(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> str | dict[str, Any]:
    """Sales specialist triage tool."""
    return await _run_specialist("sales", summary, history or [])


async def specialist_billing(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> str | dict[str, Any]:
    """Billing specialist triage tool."""
    return await _run_specialist("billing", summary, history or [])


async def specialist_support(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> str | dict[str, Any]:
    """Support specialist triage tool."""
    return await _run_specialist("support", summary, history or [])


async def specialist_retention(
    summary: str, history: list[dict[str, Any]] | None = None,
) -> str | dict[str, Any]:
    """Retention specialist triage tool."""
    return await _run_specialist("retention", summary, history or [])


def register_specialist_tools(tool_executor: Any) -> None:
    """Register all mock specialist tools in a ToolExecutor."""
    tool_executor.register_tool("specialist_sales", specialist_sales)
    tool_executor.register_tool("specialist_billing", specialist_billing)
    tool_executor.register_tool("specialist_support", specialist_support)
    tool_executor.register_tool("specialist_retention", specialist_retention)
