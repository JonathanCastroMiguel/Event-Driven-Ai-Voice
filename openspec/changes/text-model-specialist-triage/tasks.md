## 1. Configuration and Client Setup

- [ ] 1.1 [BE] Add `specialist_model: str = "gpt-4o"` and `specialist_timeout_s: float = 5.0` to `Settings` in `config.py`.
- [ ] 1.2 [BE] Add `configure(api_key: str, model: str, timeout_s: float)` and `close()` functions to `specialist_tools.py`. `configure` creates a module-level `httpx.AsyncClient` with `Authorization: Bearer <api_key>` default header. `close` shuts it down gracefully.
- [ ] 1.3 [BE] Call `specialist_tools.configure(settings.openai_api_key, settings.specialist_model, settings.specialist_timeout_s)` in `main.py` lifespan startup, and `specialist_tools.close()` in shutdown.

## 2. Specialist Tools — Text Model Integration

- [ ] 2.1 [BE] Extract the shared text model call into a private async function `_call_text_model(system_prompt: str, user_message: str) -> str | None`. It POSTs to `https://api.openai.com/v1/chat/completions` with the configured model, `max_tokens=200`, `temperature=0.8`. Returns `choices[0].message.content` on success, `None` on any failure (timeout, HTTP error, empty content). Logs warnings on failure.
- [ ] 2.2 [BE] Refactor each specialist tool (`specialist_billing`, `specialist_sales`, `specialist_support`, `specialist_retention`) to: (a) build the system prompt (existing triage instructions) and user message (summary + formatted history), (b) call `_call_text_model`, (c) if successful return the text as `str`, (d) if failed fall back to returning the current `response.create` dict (existing `_wrap_response_create` behavior).
- [ ] 2.3 [BE] When the httpx client is not configured (None), skip the text model call and fall back to returning the `response.create` dict. Log a warning.

## 3. Coordinator — Literal Vocalization

- [ ] 3.1 [BE] In `coordinator.py` `_on_model_router_action`, after the specialist tool returns successfully: detect if `tool_result.payload` is a `str` (text model response). If so, wrap it in a `response.create` dict with a directive instruction (e.g., `"Say exactly the following to the customer, without adding or changing anything: <text>"`). Emit as `RealtimeVoiceStart` with `response_source="specialist"`.
- [ ] 3.2 [BE] If `tool_result.payload` is a `dict` (fallback path), keep existing behavior — forward the dict directly as the prompt.

## 4. Tests

- [ ] 4.1 [TEST] Unit test `_call_text_model`: mock httpx to return a successful response, verify it returns the text content. Mock a timeout, verify it returns `None` and logs a warning. Mock an HTTP error, verify fallback.
- [ ] 4.2 [TEST] Unit test specialist tools: verify that when text model succeeds, the tool returns a `str`. Verify that when text model fails, the tool returns a `response.create` dict (fallback). Verify that when client is not configured, the tool falls back without error.
- [ ] 4.3 [TEST] Unit test coordinator: verify that when `tool_result.payload` is a `str`, it wraps in a directive `response.create` dict. Verify that when `tool_result.payload` is a `dict`, it forwards directly.
- [ ] 4.4 [E2E] E2E test: simulate a full specialist routing flow with mocked text model, verify the coordinator emits a `RealtimeVoiceStart` with a directive `response.create` containing the text model's response.
