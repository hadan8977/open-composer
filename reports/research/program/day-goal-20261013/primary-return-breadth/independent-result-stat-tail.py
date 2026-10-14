# Independent HAC and exact fixed bootstrap replay from existing matrix only.
x=np.column_stack([(ret[f'{name}__20']-ret[f'{name.replace("FEDPUT","GENERIC")}__20']).to_numpy()for name in ids]);n=len(x);mu=x.mean(axis=0);u=x-mu;var=(u*u).mean(axis=0)
for k in range(1,6):var+=2*(1-k/6)*(u[k:]*u[:-k]).sum(axis=0)/n
se=np.sqrt(var/n);rng=np.random.default_rng(20261013);samp=[];maxt=[]
for _ in range(2000):
 starts=rng.integers(0,n,size=math.ceil(n/20));idx=((starts[:,None]+np.arange(20))%n).ravel()[:n];means=x[idx].mean(axis=0);samp.append(means);maxt.append(np.max(np.abs((means-mu)/se)))
crit=np.quantile(maxt,.95);paired=load('results/paired-inference.json');near(crit,paired['maxT_critical'],1e-10)
for j,name in enumerate(ids):
 t=paired['comparisons'][name];near(mu[j]*10000,t['mean_daily_bp']);near(se[j]*10000,t['HAC_se_bp']);near(np.quantile(np.array(samp)[:,j],[.025,.975])*10000,t['blockbootstrap95_mean_bp']);near((mu[j]+np.array([-1,1])*crit*se[j])*10000,t['family_maxT95_mean_bp'])
# Verify source-form contrast coefficients/HAC against exported primitive rows; no source intake.
f=pd.read_csv(R/'french-descriptive-primitives.csv',index_col=0,parse_dates=True);fs=load('results/french-source-form-diagnostic.json')['results'];fchecks=0
for seg,mask in [('full2015_2026Aug',np.ones(len(f),bool)),('2017_2021',(f.index.year>=2017)&(f.index.year<=2021)),('2020_2021',(f.index.year>=2020)&(f.index.year<=2021)),('2022_2026Aug',f.index.year>=2022)]:
 for d in ['D1','D2','D3']:
  sel=f.loc[mask&f[d]&(f.late|f.odd)];want=fs[seg][d];assert len(sel)==want['N']
  if len(sel)<10:assert want['contrast']is None;continue
  xx=np.column_stack([np.ones(len(sel)),sel.late.to_numpy(dtype=float)]);yy=sel.MktRF.to_numpy();coef=np.linalg.lstsq(xx,yy,rcond=None)[0];scores=pd.DataFrame(xx*(yy-xx@coef)[:,None],index=sel.index).reindex(f.index[mask],fill_value=0).to_numpy();meat=scores.T@scores
  for k in range(1,6):cv=scores[k:].T@scores[:-k];meat+=(1-k/6)*(cv+cv.T)
  br=np.linalg.inv(xx.T@xx);near(coef[1]*10000,want['late_minus_odd_daily_bp']);near(np.sqrt((br@meat@br)[1,1])*10000,want['HAC5_se_bp']);fchecks+=1
