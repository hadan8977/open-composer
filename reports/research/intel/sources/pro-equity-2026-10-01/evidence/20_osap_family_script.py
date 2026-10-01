import pandas as pd, numpy as np
d=pd.read_csv('/tmp/pe/ls_wide.csv',parse_dates=['date']).set_index('date')
sd=pd.read_csv('/tmp/pe/sigdoc.csv').set_index('Acronym')
fam={
'value':['BM','BMdec','EP','SP','CF','cfp','AM','EBM','EntMult','NetPayoutYield','PayoutYield','IntanBM','IntanSP','IntanEP','BPEBM'],
'quality/profit':['GP','OperProf','OperProfRD','CBOperProf','RoE','roaq','PS','MS','OScore','CashProd'],
'momentum':['Mom12m','Mom6m','IntMom','MomOffSeason','Mom12mOffSeason','ResidualMomentum','High52','IndMom','TrendFactor','MomVol'],
'ST reversal':['STreversal'],
'low risk/vol':['Beta','BetaFP','IdioVol3F','IdioVolAHT','RealizedVol','MaxRet','Coskewness','ReturnSkew','ReturnSkew3F','betaVIX'],
'investment':['AssetGrowth','Investment','InvestPPEInv','NOA','NetEquityFinance','XFIN','CompEquIss','ShareIss1Y','ShareIss5Y','ChInv','InvGrowth','DelEqu','DebtIssuance'],
'PEAD/earnings mom':['EarningsSurprise','AnnouncementReturn','EarnSupBig','RevenueSurprise','NumEarnIncrease','EarningsStreak','REV6','SurpriseRD'],
'analyst revisions/recs':['AnalystRevision','ChangeInRecommendation','UpRecomm','DownRecomm','ConsRecomm','FEPS','sfe','ChNAnalyst','EarningsForecastDisparity','PredictedFE','ForecastDispersion','AnalystValue'],
'short interest/shorting':['ShortInterest','IO_ShortInterest','Recomm_ShortInterest','CPVolSpread','dCPVolSpread','RIVolSpread','SmileSlope'],
'insider/activism':['Activism1','Activism2'],
}
def stat(x):
    x=x.dropna(); 
    return (x.mean(), x.mean()/(x.std()/np.sqrt(len(x))) if len(x)>2 else np.nan, len(x))
rows=[]
for f,l in fam.items():
    for p in l:
        if p not in d.columns: continue
        r=d[p]
        ss=sd.loc[p,'SampleStartYear']; se=sd.loc[p,'SampleEndYear']; pub=sd.loc[p,'Year']
        ins=r[(r.index.year>=ss)&(r.index.year<=se)]
        post=r[r.index.year>se]
        row=dict(family=f,pred=p,pub=pub,sample=f"{ss}-{se}",weight=sd.loc[p,'Stock Weight'],
            ins=ins.mean(), post_pub_to_2014=r[(r.index.year>se)&(r.index.year<=2014)].mean(),
            y2005_14=r[(r.index.year>=2005)&(r.index.year<=2014)].mean(),
            y2015_24=r[(r.index.year>=2015)].mean(), t2015_24=stat(r[r.index.year>=2015])[1],
            y2020_24=r[r.index.year>=2020].mean(),
            y2022=r[r.index.year==2022].mean(),y2023=r[r.index.year==2023].mean(),y2024=r[r.index.year==2024].mean())
        rows.append(row)
t=pd.DataFrame(rows)
pd.set_option('display.width',250); pd.set_option('display.max_rows',300)
print(t.round(2).to_string(index=False))
g=t.groupby('family')[['ins','y2005_14','y2015_24','y2020_24','y2022','y2023','y2024']].mean().round(2)
g['n']=t.groupby('family').size()
print(g)
t.round(3).to_csv('/tmp/pe/osap_family_table.csv',index=False)
