# Research workflow

A Worker runs a preregistered family on shared lab adapters. A fresh Lead accepts or rejects its economic conclusions in one reception. [control.json](../control.json) records the research switch. The approved brief points to the spec and scope. Research runs on native Windows under the finite driver. Read [project rules](../docs/rules.md) for authority and [workflow.json](workflow.json) for installed roles.

## Register and run

1. Before outcomes, freeze the compact `experiment.json` and selectable starts in the direction’s trial ledger. Bind the mechanism to dated evidence, decision and fill clocks, label maturity, fold transforms, account costs and seals. Set the recent primary window and its greater weight prospectively.
2. Compare the trained non-price candidate to the practitioner rule and a matched price-only model. Group the controls, cost tiers, attribution and episode removals that answer the same decision in one batch. Register the selection rule and multiple-testing correction for the selectable claims, such as the Benjamini–Yekutieli adjustment used for the two A2 claims. Retain failed starts and prior exposure. Controls and cost views keep their declared status.
3. The Worker writes the approved spec to its phase folder. The driver resolves the adapter and launches the numerical batch detached. All agents yield until the terminal event. The original Worker validates the bounded Results packet. The fresh Lead receives it and inspects linked fills, account and fit ledgers to judge the frozen contrasts.
4. Report recent after-cost dollars and drawdown, what changed at trade level, and sensitivity to concentrated gains. A further batch needs a decision the completed family leaves open. Existing studies keep their frozen gates. Paper and orders require their own authority.

[Executed spec](proof_a3_exposure/experiment.json) · [Trial registration](proof_a3_exposure/registration.md) · [Shared batch entry points](lab/README.md) · [Worker handoff and recovery](../docs/research-tools.md#waiting-and-checkpoints)

## Driver

```powershell
Set-Location C:\OpenComposer\repo
$python = '.\.venv\Scripts\python.exe'
$direction = '<direction>'
$id = '<run-id>'
& $python scripts/research_round.py preview
& $python scripts/research_round.py init $direction
& $python scripts/research_round.py run $direction --run-id $id --timeout-seconds 86400 --review reuse --follow
& $python scripts/research_round.py resume $direction --run-id $id --timeout-seconds 86400 --follow
```

Use `run` for a new round and `resume` for its saved phases, session and jobs. Omit `--follow` for a single family. Each direction holds `brief.md` (up to 1,000 bytes), `decisions.tsv`, `trials.jsonl`, engine-written `results.json` and native evidence. The driver records one board row per round. Optional execution counts and accepted conclusions are recorded separately. Search the scoped [local index](../docs/research-tools.md) before registering new work.

Use `plan` review for new or materially changed science, `reuse` for accepted scope, and `result` or `both` when independent decisive-result or paper review is required. Reviewers cannot accept their own work. A revised plan ends the series. Correct the brief in the same direction before a new run. A park without a next brief or an expired deadline also ends the series. The driver owns the lock, wait and follow decisions.

## Measured rollout

Elapsed time runs from approved brief to independent acceptance. Total input includes cache. Counts include Worker resumes, Lead, repairs and implementer responses within each attempt. Bill cold implementation and panel preparation once. The warm proof-B limits were 13:00, 3.20M total input, 210k uncached input and 26k output.

| Run | Elapsed | Numerical job | Total input | Uncached input | Output | Efficiency verdict |
|---|---:|---:|---:|---:|---:|---|
| B attempt 1 | 23:38 | 16:27 after repair | 9,283,349 | 208,277 | 22,928 | FAIL · time and total input |
| B attempt 2, interrupted and recovered | 11:49 | 4:05 | 3,285,460 | 262,356 | 15,586 | FAIL · total and uncached input |
| B unattended repetition | 9:08 | 3:52 | 1,705,577 | 166,761 | 10,915 | PASS |
| A3 unattended, new question | 6:04 | 0:11 | 1,537,656 | 168,952 | 13,721 | PASS |

B attempt 1 included 30 implementer responses while compute was pending. B attempt 2 needed transport recovery. Counting attempt 2 and its full repetition together gives 21:10 and 5,227,393 total input, above the gate. A3’s cold build cost 8:31 and 2,738,928 input.

B recovered all 128 parity tables. Its historical patch runner stays in the proof directory. A3 exercised shared model and account code. Its primary-window non-price increment was $0 and the hypothesis failed. Both unattended runs issued zero model requests during numerical computation. Use the warm limits as a measured comparison for this rollout. Economic acceptance follows each family's own contract. [B attempt 1](levered_index_throughput/measurements.json) · [B recovery and repetition](levered_index_throughput/measurements-attempt-2.json) · [A3 measurements](proof_a3_exposure/measurements.json) · [A3 economic verdict](proof_a3_exposure/report.zh.md)
