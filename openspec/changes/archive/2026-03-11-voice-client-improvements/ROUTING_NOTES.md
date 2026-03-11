# Specialist Routing Investigation Notes

## Issue
The phrase "me han cobrado de más en la última factura" sometimes does NOT trigger
specialist routing. The model speaks about connecting to billing but does NOT call
the `route_to_specialist` function.

## Root Cause: Model Non-Determinism

This is NOT a code bug. The OpenAI Realtime API model exhibits non-deterministic
behavior where it sometimes vocalizes routing intent without executing the function call.

### Evidence from Docker Logs

**Call 1 (09e73922)** — Routing FAILED:
- User said: "me han cobrado de más en la última factura"
- Model responded verbally about connecting to billing
- `function_call_received=False` — no function call was made
- `response.done` logged with transcript mentioning billing, but no `model_router_action` event

**Call 2 (7834c7e5)** — Routing SUCCEEDED on 3rd turn:
- Turn 1: Model asked clarifying question (no routing)
- Turn 2: Model responded but still no function call
- Turn 3: Model correctly called `route_to_specialist(department="billing", ...)`
- `function_call_received=True`

### Conclusion
The router prompt rules are correct — "me han cobrado de más en la factura" is a
textbook billing case that matches `billing: invoices, charges, payments, refunds`.
The failure is the model's non-deterministic behavior in executing function calls.

## Mitigation
Updated `decision_rules` in `router_prompt.yaml` with:
1. Explicit "MANDATORY" and "NON-OPTIONAL" reinforcement for function calling
2. Negative example: "NEVER say you will connect without calling the function"
3. End-of-prompt recency reinforcement: "REMINDER: When routing, MUST call function"
4. Concrete examples mapping phrases to function calls

## Alternative Test Phrases (Higher Routing Reliability)
- "Quiero hablar con alguien de facturación"
- "Necesito que revisen un cargo en mi cuenta"
- "Tengo un problema con mi factura, necesito ayuda"
- "Me están cobrando algo que no reconozco"
- "Quiero cancelar mi servicio" (retention)
- "Mi internet no funciona desde ayer" (support)
- "Quiero cambiar a un plan más barato" (sales)
