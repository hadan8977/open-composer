# ruff: noqa: E402 -- Runtime paths and frozen-source imports initialize in order.
"""Use the installed Torch environment for unchanged saved-model inference only."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from open_composer.paper_runtime.six.paper_target_input_controls import (
    receive_action_lineage,
    receive_current_paper_maintenance,
    require_prior_sequence,
)

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
from open_composer.paper_runtime.paths import repo_root
from open_composer.paper_runtime.source_loader import load_source

REPO = repo_root()
root = args.output.resolve()
assert root.is_relative_to(REPO / "reports/paper/diagnostics")
assert not (root / "current-lstm-inference.json").exists(), "Saved inference exists; do not replay"
t = (
    REPO
    / "reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020"
)
available = (
    int(
        next(
            v.split()[1]
            for v in Path("/proc/meminfo").read_text().splitlines()
            if v.startswith("MemAvailable:")
        )
    )
    * 1024
)
assert available >= 524288000, "Preserve actual500MiB reserve after Torch import"
old = json.loads((t / "input/LSTM/output.json").read_text())
method_path = (
    t.parent.parent
    / "return-line-replenishment-20261016/direct-position-learning-20261016/torch_method.py"
)
method = load_source("original_lstm_math", method_path, root=REPO)
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)
torch.backends.mkldnn.enabled = False
receive_current_paper_maintenance()
receive_action_lineage(root)
require_prior_sequence(root, np)
z = np.load(root / "current-lstm-sequence.npz", allow_pickle=False)
x = z["features"]
vol = z["vol"]
expected = json.loads((root / "lstm-input-QA.json").read_text())
assert (
    len(x) == expected["full_sequence_rows"]
    and len(x) == expected["annual_sessions"] + 63
    and vol.shape == (len(x), 10)
)
predictions = []
errors = []
for context in old["model_context"]:
    p = Path(context["checkpoint"]["path"])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == context["checkpoint"]["sha256"]
    ckpt = torch.load(p, map_location="cpu", weights_only=True)
    prep = context["preprocessing"]
    full = np.clip(x, prep["low"], prep["high"])
    full = np.where(np.isfinite(full), full, prep["median"])
    xt = torch.from_numpy(((full - prep["mean"]) / prep["std"]).astype(np.float32))
    model = method.PositionLSTM()
    model.load_state_dict(ckpt["state"], strict=True)
    model.eval()
    receive_current_paper_maintenance()
    with torch.no_grad():
        _, hidden = model(xt[:63])
        logits = []
        for i in range(63, len(xt), 63):
            q, hidden = model(xt[i : i + 63], hidden)
            logits.append(q)
            hidden = tuple(z.detach() for z in hidden)
        score = torch.cat(logits)
        w = method.weights(score, torch.from_numpy(vol[63:]), "MEANNET")
    original = np.load(context["saved_forecast"]["path"], allow_pickle=False)
    error = float(np.max(np.abs(score[:185].numpy() - original["raw_scores"])))
    assert error <= 2e-6, f"Original recurrent prefix changed: {error}"
    errors.append(error)
    predictions.append(w[-1].tolist())
value = {
    "weights": np.mean(predictions, axis=0).tolist(),
    "prefix_max_errors": errors,
    "torch_version": torch.__version__,
    "new_fits": 0,
    "new_inferences": 2,
    "full_sequence_rows": len(x),
    "annual_sessions": len(x) - 63,
    "per_seed_feasible_weights": predictions,
    "source_sequence_sha256": hashlib.sha256(
        (root / "current-lstm-sequence.npz").read_bytes()
    ).hexdigest(),
    "actual_available_bytes_after_imports": available,
}
(root / "current-lstm-inference.json").write_text(json.dumps(value, indent=2) + "\n")
print(json.dumps(value), flush=True)
