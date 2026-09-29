# External Brief: h20260928_17_filing_risk_labels

Full machine-readable version: `external-brief.json`. 8 sources read in full, 4 of them primary
papers (Dolphin et al. 2601.15247, Choi et al. 2510.03195, Campbell et al. 2014, Kakushadze 2016).

## Key findings

1. **Dolphin et al.** (arxiv 2601.15247): a 3-stage LLM pipeline extracts structured 10-K risk
   factors that carry real economic structure (63% higher within-industry similarity, Cohen's
   d=1.06) -- validates the CONSTRUCTION, not forward-return predictive power.
2. **Choi et al.** (arxiv 2510.03195, LinqAlpha/MIT/BlackRock/Blackstone/JPM/Fidelity/Qube/State
   Street/UT-Austin/U-Florida/UNIST): an LLM-structured disclosure-change feature beats an NER
   baseline by >2x risk-adjusted alpha -- the closest real evidence that this class of feature can
   add predictive power over a simpler baseline (different document type: earnings calls, not
   10-K/8-K, which we do not have locally).
3. **Campbell et al. (2014)**: the raw (non-LLM) 10-K risk-factor section already carries real
   information content (correlates with systematic/idiosyncratic risk, info asymmetry, firm value)
   -- the baseline this LLM feature needs to add something beyond.
4. **Scope narrowing (disclosed, not silent)**: our local text inventory is 8-K EX-99.1 press
   releases, not 10-K Item 1A risk-factor sections -- this pilot extracts risk_score from 8-K text,
   a real change from the plan's '10-K/8-K' framing.
5. **Baseline reference**: Loughran-McDonald's dictionary is the standard non-LLM comparison point
   if this feature clears its own bar.

See `direction-review.json` for the full receipt and
`reports/harness/source_cards/h20260928_17_filing_risk_labels.jsonl` for verified source cards.
