## 1. HTTP Agent Dispatch

- [ ] 1.1 [BE] Add `dispatch_http_agent(url, auth, department, summary, history, language) -> str | None` to `specialist_tools.py`. Uses the shared `httpx.AsyncClient`. Sends POST with JSON body `{department, summary, history, language}`. Parses response as plain text or JSON `{text}`. Returns `None` on timeout, HTTP error, or empty response. Logs warnings on failure.
- [ ] 1.2 [BE] Add `get_client() -> httpx.AsyncClient | None` to `specialist_tools.py` exposing the module-level client for external use.
- [ ] 1.3 [BE] If `auth` is not None, inject `Authorization: Bearer <auth>` header on the HTTP request. If `auth` is None, omit the header.

## 2. ToolConfig Validation

- [ ] 2.1 [BE] Update `ToolConfig` in `model_router.py`: restrict `type` to `"internal" | "http"`. Add validation in `load_router_prompt` (or `load_router_prompt_from_dict`): if `type == "http"` and `url` is None or empty, raise `ValueError`.

## 3. Coordinator Dispatch Refactor

- [ ] 3.1 [BE] In `coordinator.py` `_on_model_router_action`, replace `ToolExecutor`-based dispatch with type-based dispatch: resolve `tool_config = self._router_prompt_builder.get_department_tool(department)`. If `tool_config.type == "http"`, call `dispatch_http_agent`. If `tool_config.type == "internal"`, call the internal text-model flow (`_call_text_model` with department system prompt). If `tool_config is None`, follow direct response flow.
- [ ] 3.2 [BE] Extract language from conversation history (last user message) or default to `"es"`. Pass it to `dispatch_http_agent`.
- [ ] 3.3 [BE] Keep the "say exactly" directive wrapping for both `http` and `internal` dispatch results (str → response.create dict). Keep apology fallback for None results.

## 4. Remove Hardcoded Specialist Tools

- [ ] 4.1 [BE] Remove `specialist_billing`, `specialist_sales`, `specialist_support`, `specialist_retention` functions from `specialist_tools.py`. Keep `_call_text_model`, `_DEPARTMENT_SYSTEM_PROMPTS`, `_TRIAGE_FRAMEWORK`, `configure`, `close`, `get_client`, and `dispatch_http_agent`.
- [ ] 4.2 [BE] Remove `register_specialist_tools` function from `specialist_tools.py`.
- [ ] 4.3 [BE] Remove the `register_specialist_tools` call from `main.py` (if it exists) and any `ToolExecutor` specialist tool registration.

## 5. Internal Dispatch Function

- [ ] 5.1 [BE] Add `dispatch_internal_agent(department, summary, history) -> str | None` to `specialist_tools.py`. Looks up system prompt from `_DEPARTMENT_SYSTEM_PROMPTS[department]`, formats user message with history, calls `_call_text_model`. Returns text on success, None on failure. This replaces the removed `specialist_*` functions.

## 6. Tests

- [ ] 6.1 [TEST] Unit test `dispatch_http_agent`: mock httpx to return plain text response (success), JSON `{text}` response (success), timeout (returns None), HTTP error (returns None), empty body (returns None). Test auth header presence/absence.
- [ ] 6.2 [TEST] Unit test `dispatch_internal_agent`: mock `_call_text_model` to return text (success) and None (fallback). Verify correct system prompt is used per department.
- [ ] 6.3 [TEST] Unit test coordinator dispatch: mock `get_department_tool` to return `ToolConfig(type="http", url="...", auth="token")` — verify `dispatch_http_agent` is called. Mock `ToolConfig(type="internal")` — verify internal flow is called. Mock `None` — verify direct flow.
- [ ] 6.4 [TEST] Unit test `ToolConfig` validation: verify `type="http"` with `url=None` raises `ValueError`. Verify `type="internal"` with `url=None` is valid.
- [ ] 6.5 [E2E] E2E test: simulate full specialist routing with mocked HTTP agent, verify filler + directive response.create emitted with agent's text.
