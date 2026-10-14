"""Presentation-only final output seal under the existing single completion budget."""

import runpy
from pathlib import Path

from hf_completion_resources import apply_job_limit

P = Path(__file__).resolve().parent


if __name__ == "__main__":
    apply_job_limit("report")
    for name in ["write_hf_costed_result.py", "interpret_hf_costed_result.py",
                 "write_hf_final_support.py"]:
        runpy.run_path(str(P / name), run_name="__main__")
    (P / "completion-resource-ledger-at-result.json").write_bytes(
        (P / "completion-resource-ledger.json").read_bytes()
    )
    runpy.run_path(str(P / "build_hf_complete_manifest.py"), run_name="__main__")
