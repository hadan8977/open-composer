"""r6 affected checks, synthetic native accounts only; no market/Frame scan."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from decimal import Decimal

resource.setrlimit(resource.RLIMIT_CPU,(58,62))
R=Path.cwd()
P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D=P/"revisions/consumer-r6"
sys.path.insert(0,str(P/"code"))
import consumer_admission as gate
authority=gate.authority()
assert os.sched_getaffinity(0)=={0}
def load(p): return json.loads(p.read_text())
def bind(p):
    assert p.stat().st_size<2_000_000,p
    with p.open("rb") as f: sha=hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
def walk(x):
    if isinstance(x,dict):
        if "path" in x and "sha256" in x: yield x
        else:
            for v in x.values(): yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)

packet=load(D/"review-packet.json")
assert bind(D/"review-packet.json")["sha256"]=="4f6c129f634c6efe1fabcea4cd9247b08df01bd27e1c2ff43d06e6e7afe618f0"
assert bind(P/"consumer-implementation-manifest.json")==packet["manifest"]
old=load(D/"before-consumer-implementation-manifest.json")
new=load(P/"consumer-implementation-manifest.json")
oldmap={b["path"]:b for b in walk(old)}
fresh=[];inherited=[]
for b in list(walk(new))+list(walk(packet)):
    if oldmap.get(b["path"])==b: inherited.append(b);continue
    a=bind(R/b["path"])
    assert a["sha256"]==b["sha256"] and ("bytes" not in b or a["bytes"]==b["bytes"]),b
    fresh.append(a)
for k in ("approved_plan","science_review","scientific_contracts","cases","input","prepared_feature_prefix","complete_prepared_frames"):
    assert new[k]==old[k],k
rows=[load(p) for p in (P/"economic-results/reservations").glob("*.json")]
assert len(rows)==3 and all(r["status"]=="settled" for r in rows)
consumed=sum(Decimal(str(r["charged_CPU"])) for r in rows)
assert consumed==Decimal("1831.81333")
assert Decimal("7176.73")-consumed==Decimal("5344.91667")
jan=load(R/packet["completed_actual_January"]["path"])
assert len(jan["components"])==1 and jan["components"][0]["month"]=="2024-01" and jan["components"][0]["exact_interpreted_parity"] is True
reconcile=load(D/"first-probe-reconciliation.json")
assert Decimal(str(reconcile["charge"]))==Decimal("156.83")
assert Decimal(str(reconcile["outer_CPU"]))+5==Decimal("156.83")
v=dict(manifest=packet["manifest"],packet=bind(D/"review-packet.json"),authority=authority["task"],fresh_small_bindings=fresh,inherited_not_rehashed=inherited,consumed_CPU=str(consumed),original_remaining_CPU="5344.91667",actual_Jan_only_inherited=True,March_old_RAM_witness_not_claimed_durable=True,checks=[],market_Frame_source_scan=False)
def save(): (D/"independent-verification.json").write_text(json.dumps(v,indent=2)+"\n")
save()

import native_shared_feed as shared
import verify_shared_feed as verify
import verify_feed_reuse as reuse

# Capture complete string representations before both engines see the same
# immutable objects, supplementing author's bid-only quote witness.
original=shared.native_month
captured=[]
def snapshot(data):
    books,quotes,boundaries,_=data
    return ([str(x) for x in books],[str(x) for x in quotes],[(x.data.stage,x.data.frames_json,x.ts_event) for x in boundaries])
def observed(*args,**kw):
    data=original(*args,**kw)
    captured.append((data,snapshot(data)))
    return data
shared.native_month=observed
try:
    verify.main()
    assert all(snapshot(data)==before for data,before in captured)
    v["checks"].append("3 single-versus-two-account witnesses and feedback recovery/re-pause pass")
    v["checks"].append(dict(full_book_quote_boundary_objects_unchanged_after_both_engines=True,generated_intervals=len(captured)))
    save()
    old_source=verify.source
    def no_shape(**kw):
        packets=old_source(**kw)
        for p in packets:
            for row in p["frames"]: row["frame"]["shape_ok"]=False
        return packets
    verify.source=no_shape
    try:
        verify.verify_case({},"O-H-L-C")
        assert all(snapshot(data)==before for data,before in captured)
        v["checks"].append("Extra shape-false P_SYSTEM market/P_EMA capped single/shared witness passes; EMA exemption preserved")
    finally: verify.source=old_source
finally: shared.native_month=original
save()
argv=sys.argv
sys.argv=["verify_feed_reuse.py","--quick"]
try: reuse.main()
finally: sys.argv=argv
v["checks"].append("4 reference/reuse native witnesses and5 complete-field decoder equalities pass")
v["synthetic_engine_count"]=24
v["completed"]=True
u=resource.getrusage(resource.RUSAGE_SELF)
v["own_CPU"]=u.ru_utime+u.ru_stime;v["RSS_KiB"]=u.ru_maxrss
save()
print(json.dumps(dict(status="passed",checks=v["checks"],own_CPU=v["own_CPU"])))
