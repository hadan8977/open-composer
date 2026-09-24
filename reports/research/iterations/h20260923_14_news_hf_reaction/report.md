# h20260923_14 news HF reaction -- report

- Feature: signed high-frequency news reaction (Jiang, Li & Wang), 2024-01..2026-09, built by `scripts/build_news_hf_reaction.py`.
- Cards (preregistered in `reports/research/signal-cards/news-hf-v1-manifest.json`):
  - NHF01 raw rank: IC -0.005 (t -0.9), reject.
  - NHF02 5-day-sum rank: IC -0.003 (t -2.5, wrong sign), reject.
  - NHF03 p90 event: CAR -0.29% at 5d (t -1.9, 20,448 events), reject.
- Verdict: stop. Details and caveats are in `decision-record.md`.
- Pass flags:
  - workflow_pass true;
  - research_pass false;
  - llm_contribution_pass n/a (no LLM input);
  - ml_contribution_pass n/a;
  - paper_ready_pass false.
