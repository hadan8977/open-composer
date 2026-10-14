"""Real inherited CPU limits only; no input, native validation or economics."""
import json
import resource
import subprocess
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
P = D.parents[1]
sys.path.insert(0, str(P / "code"))
import consumer_admission as gate

gate.receipt = lambda _: dict(empirical_CPU_upper=600, runtime_actual_CPU=0, launcher_unknown_CPU=5)
gate.usage = lambda: (0, 0)
gate.empirical_limit("inert-only-no-reservation")
before = resource.getrlimit(resource.RLIMIT_CPU)
child = """import json,resource
before=resource.getrlimit(resource.RLIMIT_CPU)
try:
 resource.setrlimit(resource.RLIMIT_CPU,(1198,1199))
 print(json.dumps(dict(before=before,after=resource.getrlimit(resource.RLIMIT_CPU),raised=True)))
except Exception as e:
 print(json.dumps(dict(before=before,raised=False,error=type(e).__name__+str(e))))
"""
r = subprocess.run([sys.executable, "-c", child], text=True, capture_output=True, timeout=3)
assert r.returncode == 0, r.stderr
result = json.loads(r.stdout)
resource.setrlimit(resource.RLIMIT_CPU, (1198, 1199))
standalone = resource.getrlimit(resource.RLIMIT_CPU)
assert result["before"] == [594, 595] and result["after"] == [1198, 1199]
assert standalone == (1198, 1199)
(D / "independent-limit-probe-result.json").write_text(json.dumps(dict(
    parent_empirical_limits=before, child=result, standalone_runtime_limits=standalone,
    actual_environment_only=True, no_heavy_work=True, no_author_ledger_mutation=True,
    prior_child_probe_syntax_error_preserved=True,
), indent=2)+"\n")
