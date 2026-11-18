---
name: risk-reviewer
description: Review a candidate signal, strategy report, and market context for manual or paper-trading risk.
---

Produce an advisory [ReviewCard](../../../open_composer/models/review_card.py) linked to the existing `signal_id`: catalyst, evidence, risks, invalidation, action suggestion, and a `consider`, `avoid` or `wait` verdict. Preserve required identity, timestamp, confidence and model fields.

Flag sample/fixture/cache-fallback/trial data, missing benchmark families, short samples, low trade counts and LLM fallback as evidence limits. Use [the reporting definitions](../../../docs/owner-reporting.zh.md) to separate workflow, research, model contribution and paper readiness before recommending a next action. Real-money automatic execution remains out of scope.
