import json, urllib.parse, urllib.request, time, datetime as dt
base="https://www.dolthub.com/api/v1alpha1/post-no-preference/options?q="
def run(q, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(base+urllib.parse.quote(q), timeout=150) as r:
                d=json.load(r)
            if d.get("query_execution_status")=="Success":
                return d.get("rows",[])
            print("err", d.get("query_execution_message","")[:120], flush=True)
        except Exception as e:
            print("exc", repr(e)[:120], flush=True)
        time.sleep(10*(k+1))
    return None
out={}
months=[]
y,m=2024,1
while (y,m)<=(2026,10):
    months.append((y,m)); m+=1
    if m==13: y,m=y+1,1
for (y,m) in months:
    a=f"{y}-{m:02d}-01"; ny,nm=(y+1,1) if m==12 else (y,m+1); b=f"{ny}-{nm:02d}-01"
    rows=run(f"SELECT `date`, COUNT(*) AS n FROM volatility_history WHERE `date` >= '{a}' AND `date` < '{b}' GROUP BY `date` ORDER BY `date`")
    out[a]=rows
    print(a, None if rows is None else len(rows), flush=True)
    json.dump(out, open("/tmp/p6cov/counts.json","w"))
print("DONE", flush=True)
