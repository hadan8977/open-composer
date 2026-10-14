import json,hashlib,resource,os
from pathlib import Path
from html.parser import HTMLParser
resource.setrlimit(resource.RLIMIT_CPU,(30,35));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).resolve().parent;checked=[]
packet=json.loads((P/'scientific-review-packet.json').read_text())
for b in packet['bindings']:
 p=Path(b['path']);raw=p.read_bytes();assert len(raw)==b['bytes'] and hashlib.sha256(raw).hexdigest()==b['sha256'],str(p)
 checked.append(b)
assert hashlib.sha256((P/'scientific-plan.json').read_bytes()).hexdigest()=='ee170cfb79139b85bc51cf5dc356b66d9c88a9c402c8fe7bf8b60925457db617'
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.text=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['script','style']:self.skip+=1
 def handle_endtag(self,tag):
  if tag in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,text):
  if not self.skip and text.strip():self.text.append(text.strip())
p=Parser();p.feed((P/'study-figure-source/authored_short_study_html.bin').read_text());text='\n'.join(p.text)
(P/'independent-source-visible-text.txt').write_text(text+'\n')
for term in ['prior day','hourly','ORL','stop','short study']:
 start=0;segments=[]
 while len(segments)<5:
  pos=text.lower().find(term,start)
  if pos<0:break
  segments.append(text[max(0,pos-180):pos+750]);start=pos+len(term)
 print(term, json.dumps(segments,ensure_ascii=False))
out=dict(status='all_direct_bindings_match',bindings=checked,images_visually_inspected_by_reviewer=['CHPT_hourly','SENS_hourly','TSLA_hourly','SMCI_hourly','CHPT_daily','SENS_daily','TSLA_daily'],source_text_extracted_from_actual_HTML=True,new_network_market_economics=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-scientific-verification.json').write_text(json.dumps(out,indent=2)+'\n')
