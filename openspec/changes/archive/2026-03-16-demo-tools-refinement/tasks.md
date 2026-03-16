## 1. Refactor shared prompt into per-department prompts

- [x] 1.1 Remove `DEPARTMENTS` dict and `_build_specialist_payload` function
- [x] 1.2 Add `_format_history_block(history)` shared helper (extract from current code)
- [x] 1.3 Add `_wrap_response_create(instructions)` shared helper to build the payload dict
- [x] 1.4 Write `_build_sales_prompt(summary, history)` with sales-specific triage examples (current plan, desired features, budget)
- [x] 1.5 Write `_build_billing_prompt(summary, history)` with billing-specific triage examples (invoice number, charge date, amount)
- [x] 1.6 Write `_build_support_prompt(summary, history)` with support-specific triage examples (device/service, error messages, when it started)
- [x] 1.7 Write `_build_retention_prompt(summary, history)` with retention-specific triage examples (reason for leaving, tenure, what would change mind)
- [x] 1.8 Update the four `specialist_*` async functions to call their respective prompt builders

## 2. Language handling

- [x] 2.1 Ensure all prompts reference department names only in English
- [x] 2.2 Add explicit instruction in each prompt: "Translate the department name to match the customer's language"

## 3. Tests

- [x] 3.1 Add test: each specialist returns distinct instructions (not identical prompts)
- [x] 3.2 Add test: no prompt contains hardcoded Spanish translations ("ventas", "facturación", "soporte técnico", "retención")
- [x] 3.3 Add test: each prompt contains department-specific triage example keywords
