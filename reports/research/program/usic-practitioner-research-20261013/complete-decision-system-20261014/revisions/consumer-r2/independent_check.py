"""Bounded independent r2 difference checks; no source or economic execution."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

ROOT = Path.cwd()
P = ROOT / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D = P / "revisions/consumer-r2"
sys.path.insert(0, str(P / "code"))
import consumer_admission as gate

assert os.sched_getaffinity(0) == {0}
authority = gate.authority()

def bindings(x):
    if isinstance(x, dict):
        if "path" in x and "sha256" in x:
            yield x
        else:
            for v in x.values():
                yield from bindings(v)
    elif isinstance(x, list):
        for v in x:
            yield from bindings(v)

def check(b):
    path = ROOT / b["path"]
    assert path.stat().st_size < 3_000_000, path
    with path.open("rb") as f:
        actual = hashlib.file_digest(f, "sha256").hexdigest()
    assert actual == b["sha256"], path
    assert "bytes" not in b or path.stat().st_size == b["bytes"], path
    return b

old = json.loads((D / "before/consumer-implementation-manifest.json").read_text())
new = json.loads((P / "consumer-implementation-manifest.json").read_text())
oldmap = {b["path"]: b for b in bindings(old)}
fresh, inherited = [], []
for b in bindings(new):
    if oldmap.get(b["path"]) == b:
        inherited.append(b)
    else:
        fresh.append(check(b))
for name, expected in [
    ("consumer-review-packet.json", "ea172b4641c88c82f9555f53015330a31de2bbba12292fe6ceca328c2eac7a2c"),
    ("consumer-implementation-manifest.json", "10705c4e0253f324d7dc6a92294c904c66e8327a0ac5696f1b43492ea612ef1b"),
    ("revisions/consumer-r2/affected-diff.json", "3f3ec7f2ed0e6455dcb8d9a0721e20d0291525bfe7fa4b96dce519f0ae3107ea"),
]:
    fresh.append(check(dict(path=str((P / name).relative_to(ROOT)), sha256=expected)))

# Real kernel inheritance probe, with no native/data/model calls or CPU work.
# Child starts from normal inherited limits before reviewer tightens its own cap.
probe = '''import json,resource,subprocess,sys
sys.path.insert(0,sys.argv[1])
import consumer_admission as g
g.receipt=lambda _: dict(empirical_CPU_upper=600,runtime_actual_CPU=0,launcher_unknown_CPU=5)
g.usage=lambda: (0,0)
g.empirical_limit("inert-only")
before=resource.getrlimit(resource.RLIMIT_CPU)
child_code="import json,resource; b=resource.getrlimit(resource.RLIMIT_CPU); \\\n+exec('try:\\n resource.setrlimit(resource.RLIMIT_CPU,(1198,1199))\\n print(json.dumps(dict(before=b,after=resource.getrlimit(resource.RLIMIT_CPU),raised=True)))\\nexcept Exception as e:\\n print(json.dumps(dict(before=b,raised=False,error=type(e).__name__+str(e))))')"
c=subprocess.run([sys.executable,"-c",child_code],capture_output=True,text=True,timeout=5)
try:
 resource.setrlimit(resource.RLIMIT_CPU,(1198,1199)); standalone=dict(raised=True,after=resource.getrlimit(resource.RLIMIT_CPU))
except Exception as e:
 standalone=dict(raised=False,error=type(e).__name__+str(e))
print(json.dumps(dict(empirical_parent=before,child_returncode=c.returncode,child_stdout=c.stdout,child_stderr=c.stderr,standalone=standalone)))
'''
res = subprocess.run([sys.executable, "-c", probe, str(P / "code")], capture_output=True, text=True, timeout=10)
verification = dict(
    scope="Affected bindings and actual resource-limit inheritance; old 74/input25-month checks reused",
    authority_task=authority["task"], affinity=sorted(os.sched_getaffinity(0)),
    fresh_checked=fresh, inherited_not_rehashed=inherited,
    limit_probe=dict(returncode=res.returncode, stdout=res.stdout, stderr=res.stderr),
    economic_execution=False, source_requests=0,
)
(D / "independent-diff-verification.json").write_text(json.dumps(verification, indent=2)+"\n")
assert res.returncode == 0, res.stderr
resource.setrlimit(resource.RLIMIT_CPU, (13, 14))
import pytest
rc = pytest.main([
    "-q", str(P / "code/test_consumer_revisions.py"),
    str(P / "code/test_nautilus_consumer.py"),
    "-k", "exact_task_owner or unique_combined or empirical600 or missing_active_minute",
    "--junitxml="+str(D / "independent-affected-tests.xml"),
])
verification["focused_pytest_exit"] = rc
verification["own_CPU"] = resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime
(D / "independent-diff-verification.json").write_text(json.dumps(verification, indent=2)+"\n")
raise SystemExit(rc)
