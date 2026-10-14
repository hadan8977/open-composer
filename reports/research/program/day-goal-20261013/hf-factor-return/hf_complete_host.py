"""Complete only the admitted independent host sleeves, reusing sealed forecasts."""

import json
import resource

import numpy as np
from hf_evaluate import host_contribution
from hf_features import FEATURE, P, bind, save
from hf_run_models import E, guard


def main():
    guard("accounts")
    rows = json.loads((FEATURE / "packet-row-clock.json").read_text())
    linear = json.loads((E / "linear-model-manifest.json").read_text())
    nonlinear = json.loads((E / "HGB-model-manifest.json").read_text())
    ids = linear["candidate_ids"] + nonlinear["candidate_ids"]
    prediction = np.column_stack(
        (np.load(E / "linear-predictions.npy"), np.load(E / "HGB-predictions.npy"))
    )
    host = host_contribution(prediction, ids, rows)
    definition = json.loads((P / "host-leading-availability-diff.json").read_text())
    assert host["ready"], host
    assert host["first_common_close"] == definition["observed"][
        "first_common_five_host_returns_available_close"
    ]
    assert host["rows"] == definition["observed"]["admissible_common_rows"]
    save(E / "results/host-results.json", host)
    used = resource.getrusage(resource.RUSAGE_SELF)
    save(E / "host-completion-resource.json", dict(
        completed=True, CPU_process=used.ru_utime + used.ru_stime,
        max_RSS_KiB=used.ru_maxrss, host_results=bind(E / "results/host-results.json"),
        model_retraining=False, standalone_account_replay=False,
        funded4k_model_books=40, physical_controls=4,
    ))
    print(json.dumps(dict(status="original_host_scope_complete", rows=host["rows"])))


if __name__ == "__main__":
    main()
