# External brief: h20260928_22_llm_news_momentum_filter

Eight fresh sources (2026-09-28), four papers: the target paper (Anic, Barbon, Seiz and
Zarattini 2025, arXiv:2510.26228, read via full-text pdftotext extraction for its exact
prompt, weighting formula and optimal hyperparameters, plus its own abstract page for
citation grounding), Glasserman & Lin (2023, arXiv:2309.17322, the anonymization/distraction-
effect method this round's headline neutralization follows), and He, Lv, Manela and Wu
(2025, arXiv:2502.21206, cited by the target paper itself, grounding the clean-vs-
contaminated evaluation-window split). Four provider/industry sources establish the exact
DeepSeek model identity and its disclosed knowledge cutoff (Puter's aggregator page,
DeepSeek's own release announcement and changelog) and the local news data source (Alpaca's
historical news API docs, Benzinga-sourced). See `direction-review.json` for the full
web-first reasoning and `source_evidence_bindings` for how each claim maps into the
candidate design.
