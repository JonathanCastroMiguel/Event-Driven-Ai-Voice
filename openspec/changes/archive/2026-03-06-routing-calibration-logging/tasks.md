## 1. Backend Implementation

- [x] 1.1 [BE] Add `_log_routing_completed` helper method to `Router` that takes a `RoutingResult` and emits a single `routing_completed` structured log with all calibration fields: `router_version`, `language`, `route_a_label`, `route_a_score`, `route_a_margin`, `route_b_label`, `route_b_score`, `route_b_margin`, `short_circuit`, `fallback_used`
- [x] 1.2 [BE] Compute and pass `route_a_margin` (top1 - top2) for embedding paths; use 0.0 for short-circuit paths (lexicon, short utterance)
- [x] 1.3 [BE] Compute and pass `route_b_margin` in `_classify_route_b`; set to None for non-domain paths
- [x] 1.4 [BE] Call `_log_routing_completed` before every `return` in `classify()` and `_classify_route_b()` (6 return points total: lexicon, short utterance, ambiguous Route A with LLM, non-domain embedding, Route B with LLM, Route B ambiguous without LLM, Route B confident)
- [x] 1.5 [BE] Include `router_version` from `self._registry.thresholds.version` in the log

## 2. Tests

- [x] 2.1 [TEST] Write test for lexicon short-circuit path: verify `routing_completed` log is emitted with `short_circuit="lexicon"`, `route_a_score=1.0`, `route_a_margin=0.0`
- [x] 2.2 [TEST] Write test for short utterance path: verify `routing_completed` log with `short_circuit="short_utterance"`, `route_a_score=1.0`, `route_a_margin=0.0`
- [x] 2.3 [TEST] Write test for embedding Route A (non-domain) path: verify log includes computed `route_a_margin` and `route_b_label=None`
- [x] 2.4 [TEST] Write test for Route B confident path: verify log includes `route_b_label`, `route_b_score`, `route_b_margin`
- [x] 2.5 [TEST] Write test for LLM fallback path: verify log includes `fallback_used=true`
- [x] 2.6 [TEST] Write test that `router_version` matches `thresholds.yaml` version in every log
