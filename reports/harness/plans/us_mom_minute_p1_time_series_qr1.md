# Harness Plan — us_mom_minute_p1_time_series_qr1

Generated: 2026-07-10

## Risk Domains

- leveraged_etf

## Required Skills

- backtest-forensics
- execution-reality-reviewer

## Required Artifacts

- gap_stress_report
- leveraged_etf_risk_note

## Blocking Rules

- **leveraged_etf_paper_auto_requires_stress** (blocks `paper_ready_pass`): paper_auto activation for a leveraged ETF strategy requires a completed gap_stress_report and leveraged_etf_risk_note.

