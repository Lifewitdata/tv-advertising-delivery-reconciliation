"""Exploratory, campaign-clustered uncertainty and adjusted associations."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf


def analyze(fact,config,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    due=fact[fact.due_commitment.eq(1)].copy()
    metadata={'scope':'Synthetic due, noncancelled commitments only','observations':len(due),
        'clusters':int(due.campaign_id.nunique()),'bootstrap_seed':config['seed'],
        'causal_claim':False,'bias_notes':[
            'The generator explicitly assigns station, daypart and duration effects.',
            'Future or cancelled commitments are excluded; raw feed latency affects earlier snapshots.',
            'Within-campaign resampling addresses one source of dependence, not all possible dependence.',
            'Regression intervals are nominal exploratory intervals, without multiple-testing adjustment.',
            'Synthetic associations do not establish real advertiser or station behavior.']}
    if len(due)<1000 or due.campaign_id.nunique()<20 or due.original_delivered.nunique()<2:
        metadata['regression_status']='SKIPPED: insufficient observations/clusters or outcome variation'
        (out/'statistics_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        return metadata
    grouped=due.groupby(['campaign_id','daypart']).delivered.agg(['sum','count']).unstack(fill_value=0)
    parts=sorted(due.daypart.unique())
    numerator=grouped['sum'].reindex(columns=parts,fill_value=0).to_numpy()
    denominator=grouped['count'].reindex(columns=parts,fill_value=0).to_numpy()
    rng=np.random.default_rng(config['seed'])
    weights=rng.multinomial(len(grouped),np.full(len(grouped),1/len(grouped)),size=config['bootstrap_repetitions'])
    sample_num=weights@numerator;sample_den=weights@denominator
    boot=np.divide(sample_num,sample_den,out=np.full(sample_num.shape,np.nan),where=sample_den>0)
    records=[]
    for i,part in enumerate(parts):
        low,high=np.nanquantile(boot[:,i],[0.025,0.975])
        records.append({'daypart':part,'due_commitments':int(denominator[:,i].sum()),
            'delivered':int(numerator[:,i].sum()),'delivery_rate':numerator[:,i].sum()/denominator[:,i].sum(),
            'ci_low':low,'ci_high':high,'method':f"{config['bootstrap_repetitions']} campaign-cluster bootstrap resamples"})
    pd.DataFrame(records).to_csv(out/'daypart_intervals.csv',index=False)
    if 'Prime' in parts and 'Overnight' in parts:
        difference=boot[:,parts.index('Prime')]-boot[:,parts.index('Overnight')]
        low,high=np.nanquantile(difference,[0.025,0.975])
        metadata['planned_contrast']={'comparison':'Prime minus Overnight delivery rate',
            'estimate':float((numerator[:,parts.index('Prime')].sum()/denominator[:,parts.index('Prime')].sum())-
                (numerator[:,parts.index('Overnight')].sum()/denominator[:,parts.index('Overnight')].sum())),
            'ci_low':float(low),'ci_high':float(high),'zero_excluded':bool(low>0 or high<0)}
    due['original_failure']=1-due.original_delivered
    due['duration_60']=due.duration_seconds.eq(60).astype(int)
    model=smf.glm("original_failure ~ C(daypart, Treatment(reference='Daytime')) + duration_60 + C(station_id)",
        data=due,family=sm.families.Binomial()).fit(cov_type='cluster',cov_kwds={'groups':due.campaign_id})
    if not model.converged:
        raise RuntimeError('Exploratory logistic regression failed to converge')
    intervals=model.conf_int()
    coefficients=pd.DataFrame({'term':model.params.index,'log_odds':model.params.values,
        'odds_ratio':np.exp(model.params.values),'ci_low':np.exp(intervals[0].values),
        'ci_high':np.exp(intervals[1].values),'p_value':model.pvalues.values})
    if not np.isfinite(coefficients[['log_odds','odds_ratio','ci_low','ci_high']].to_numpy()).all():
        raise RuntimeError('Nonfinite regression estimates; do not publish invalid intervals')
    coefficients.to_csv(out/'adjusted_original_failure_associations.csv',index=False)
    metadata.update(regression_status='CONVERGED',regression_outcome='Failure of original scheduled delivery',
        adjustment='Station fixed effects and 60-second duration indicator',
        standard_errors='Campaign-cluster robust',
        interpretation='Conditional associations with original delivery failure, not causal effects or future predictions')
    (out/'statistics_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata
