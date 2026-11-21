from __future__ import annotations
import sys, calendar
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

# Dates refer to BW; configurable multipliers are model assumptions, not empirical effects.
BW_HOLIDAYS={date(2026,11,1),date(2026,12,25),date(2026,12,26),date(2027,1,1),date(2027,1,6),date(2027,3,26),date(2027,3,29),date(2027,5,1),date(2027,5,6),date(2027,5,17),date(2027,5,27),date(2027,10,3),date(2027,11,1),date(2027,12,25),date(2027,12,26)}
BW_VACATIONS=[(date(2026,10,26),date(2026,10,30)),(date(2026,12,23),date(2027,1,9)),(date(2027,3,25),date(2027,4,3)),(date(2027,5,18),date(2027,5,29)),(date(2027,7,29),date(2027,9,11)),(date(2027,10,25),date(2027,10,30)),(date(2027,12,23),date(2028,1,8))]
MARKET=(date(2026,11,23),date(2026,12,22))
EXCLUDED_TERMS=('pfand','individueller betrag')

def euro(s):
    if pd.isna(s): return 0.
    return float(str(s).replace('\u00a0','').replace('€','').replace('.','').replace(',','.').strip() or '0')

def load_csv(path):
    df=pd.read_csv(path,dtype=str,encoding='utf-8-sig',keep_default_na=False)
    needed={'Datum','Typ','Menge','Beschreibung','Kategorie','Preis (brutto)'}
    if not needed.issubset(df.columns): raise ValueError('Fehlende Spalten: '+', '.join(sorted(needed-set(df.columns))))
    df['dt']=pd.to_datetime(df['Datum'],format='%d.%m.%Y, %H:%M',errors='coerce')
    if df['dt'].isna().any(): raise ValueError('Datumsspalte enthält ungültige Werte.')
    df['amount']=df['Preis (brutto)'].map(euro)
    df['qty']=df['Menge'].map(euro)
    refund=df['Typ'].str.contains('rückerstattung|erstattung',case=False,regex=True)
    # SumUp exports negative refunds; only flip positive refund amounts.
    df.loc[refund & (df['amount']>0),'amount']*=-1
    df.loc[refund & (df['qty']>0),'qty']*=-1
    df['excluded']=df['Beschreibung'].str.lower().str.contains('|'.join(EXCLUDED_TERMS),regex=True)|df['Kategorie'].str.strip().eq('')
    # FF001 marker applies to the entire transaction.
    id_cols=[c for c in df.columns if any(term in c.lower() for term in ('artikelnummer','barcode','ean','sku','gtin'))]
    marker=pd.Series(False,index=df.index)
    for col in id_cols:
        marker |= df[col].astype(str).str.strip().str.upper().eq('FF001')
    if 'Transaktionsnummer' in df.columns:
        tx=df['Transaktionsnummer'].astype(str).str.strip()
        flagged=set(tx[marker & tx.ne('')])
        df['ff001_transaction']=marker | (tx.isin(flagged) & tx.ne(''))
    else:
        df['ff001_transaction']=marker
    df['day']=df['dt'].dt.normalize()
    iso=df['dt'].dt.isocalendar()
    df['kw']=iso.year.astype(str)+'-KW'+iso.week.astype(str).str.zfill(2)
    return df

def monday(d): return d-timedelta(days=d.weekday())
def kwlabel(d): y,w,_=d.isocalendar(); return f'{y}-KW{w:02d}'
def days_of_week(d): return [d+timedelta(days=i) for i in range(7)]

def flags(d):
    return {'ferien':any(a<=d<=b for a,b in BW_VACATIONS),'feiertag':d in BW_HOLIDAYS,'markt':MARKET[0]<=d<=MARKET[1],'pendler':d.weekday()<5 and d not in BW_HOLIDAYS}

def factor(d,params):
    f=flags(d)
    result=1.
    for name in ('ferien','feiertag','markt','pendler'):
        if f[name]:result*=1+params[name]/100
    return max(0.1,result)

def growth_projection(base, observed_trend, horizon_index, growth):
    """Saturating growth: diminishing incremental gains, capped by attainable ceiling."""
    mode=growth['mode']
    if mode == 'Nur Ist-Trend':
        weekly=observed_trend
    elif mode == 'Annahme':
        weekly=growth['assumed_growth']/100.
    else:
        # With few full weeks, treat growth as assumption; gradually trust actual history.
        confidence=min(1.,max(0.,(growth['full_weeks']-2)/10.))
        weekly=(1-confidence)*growth['assumed_growth']/100.+confidence*observed_trend
    weekly=float(np.clip(weekly,-0.08,0.08))
    decay=max(1.,growth['saturation_weeks'])
    # Exponential convergence to a ceiling; negative trends decay to a nonnegative floor.
    ceiling=max(1.,growth['ceiling_pct']/100.)
    total_log=weekly*decay*(1-np.exp(-horizon_index/decay))
    multiplier=float(np.exp(total_log))
    return min(ceiling,max(0.25,multiplier)),weekly

def forecast(df,params,horizon,growth=None,history_only=False,as_of=None):
    eligible=df[~df.excluded].copy()
    if eligible.empty: raise ValueError('Keine prognosefähigen Artikelpositionen vorhanden.')
    first,last=df['dt'].min().date(),df['dt'].max().date()
    now=as_of or date.today();current=monday(now)
    week0=monday(first);week_last=monday(last)
    observed=[]
    for m in pd.date_range(week0,week_last,freq='W-MON'):
        md=m.date();start=max(md,first);end=min(md+timedelta(days=6),last)
        observed_days=(end-start).days+1
        sub=eligible[(eligible.dt.dt.date>=start)&(eligible.dt.dt.date<=end)]
        revenue=sub.amount.sum();units=sub.qty.sum()
        normalized=revenue*7/observed_days
        f=1.0 if history_only else float(np.mean([factor(d,params) for d in days_of_week(md)]))
        observed.append(dict(monday=md,kw=kwlabel(md),ist=revenue,normalized=normalized,units=units,days=observed_days,saisonfaktor=f,bereinigt=normalized/max(.1,f)))
    history=pd.DataFrame(observed)
    # A partial current KW must never be used as a full-week forecast starting value.
    # Complete its unobserved weekdays using actual sales of corresponding weekdays
    # from previously completed KW. The observed portion is never overwritten.
    current_actual=history.loc[history.monday==current,'ist']
    current_estimate=None
    current_observed_days=0
    if len(current_actual):
        current_observed_days=int(history.loc[history.monday==current,'days'].iloc[0])
        if current_observed_days<7:
            current_sum=float(current_actual.iloc[0])
            daily=eligible.groupby(eligible.dt.dt.date).amount.sum()
            prev_full=[d for d in history.loc[(history.days==7)&(history.monday<current),'monday']]
            missing_dates=[current+timedelta(days=k) for k in range(current_observed_days,7)]
            weekday_means={k:float(np.mean([daily.get(w+timedelta(days=k),0.) for w in prev_full])) for k in range(7)} if prev_full else {}
            if prev_full:
                missing_est=sum(max(0.,weekday_means[d.weekday()]) for d in missing_dates)
            else:
                missing_est=max(0.,current_sum/max(1,current_observed_days)*len(missing_dates))
            current_estimate=max(0.,current_sum+missing_est)
        else:
            current_estimate=float(current_actual.iloc[0])
    complete=history[history.days==7]
    baseline=complete if len(complete) else history
    base=max(0.,float(baseline.bereinigt.tail(4).median()))
    # Robust log-linear fit to de-seasonalized complete weeks, capped against noise.
    observed_trend=0.
    if len(complete)>=3:
        values=np.maximum(1.,complete.bereinigt.tail(8).to_numpy())
        observed_trend=float(np.clip(np.expm1(np.polyfit(np.arange(len(values)),np.log(values),1)[0]),-.08,.08))
    growth=dict(growth or {})
    growth.setdefault('mode','Hybrid')
    growth.setdefault('assumed_growth',1.5)
    growth.setdefault('saturation_weeks',16)
    growth.setdefault('ceiling_pct',160)
    growth['full_weeks']=len(complete)
    empirical=complete.normalized.tail(12).to_numpy(dtype=float)
    historical_rates=(0.,0.,0.)
    growth_samples=0
    if current_estimate is None:
        latest=history.iloc[-1]
        anchor=max(0.,float(latest.normalized))
    else:
        anchor=max(0.,float(current_estimate))
    if history_only:
        weekly_levels=[float(v) for v in empirical if v>0]
        if current_estimate is not None and anchor>0 and (len(complete)==0 or complete.monday.iloc[-1]<current):
            weekly_levels.append(anchor)
        weekly_changes=np.diff(np.log(np.maximum(weekly_levels,0.01)))
        growth_samples=len(weekly_changes)
        if growth_samples:
            center=max(0.,float(0.5*np.median(weekly_changes)+0.5*weekly_changes[-1]))
            upside=max(0.,float(np.quantile(weekly_changes,.8))-center)
            if upside<1e-9:
                upside=max(0.,float(np.max(weekly_changes))-center)
            if upside<1e-9 and growth_samples>1:
                upside=float(np.std(weekly_changes))
            confidence=min(1.,growth_samples/10.)
            base_rate=float(np.clip(center*(0.2+0.8*confidence),0.,.06))
            upside_rate=float(np.clip(upside*(0.2+0.8*confidence),0.,.05))
            historical_rates=(base_rate,base_rate+upside_rate/2,base_rate+upside_rate)
            observed_trend=float(np.expm1(center))
    rows=[]
    begin=current+timedelta(days=7)
    for i in range(horizon):
        m=begin+timedelta(days=7*i)
        f=1.0 if history_only else float(np.mean([factor(d,params) for d in days_of_week(m)]))
        if history_only:
            base_rate,moderate_rate,high_rate=historical_rates
            # Slowly diminishing weekly gains, but no hard asymptotic ceiling.
            effective_weeks=8*np.log1p((i+1)/8)
            central=anchor*float(np.exp(np.clip(base_rate*effective_weeks,-8,8)))
            low=anchor*float(np.exp(np.clip(moderate_rate*effective_weeks,-8,8)))
            high=anchor*float(np.exp(np.clip(high_rate*effective_weeks,-8,8)))
            multiplier=central/max(anchor,0.01)
            weekly=float(np.expm1(base_rate))
        else:
            multiplier,weekly=growth_projection(base,observed_trend,i+1,growth)
            central=max(0,anchor*multiplier*f)
            low_growth=dict(growth,assumed_growth=max(-2.,growth['assumed_growth']-1.5))
            high_growth=dict(growth,assumed_growth=growth['assumed_growth']+1.5)
            low_mult,_=growth_projection(base,min(observed_trend,0.),i+1,low_growth)
            high_mult,_=growth_projection(base,max(observed_trend,0.),i+1,high_growth)
            high=max(central,anchor*max(high_mult,multiplier)*f*1.1)
            low=central+0.5*(high-central)
        rows.append(dict(monday=m,kw=kwlabel(m),faktor=f,basis=central,vorsichtig=low,optimistisch=high,wachstum_faktor=multiplier,trend_ist_pct=observed_trend*100,trend_modell_pct=weekly*100,historisch_vorsichtig_pct=100*np.expm1(historical_rates[1]) if history_only else np.nan,historisch_basis_pct=100*np.expm1(historical_rates[0]) if history_only else np.nan,historisch_optimistisch_pct=100*np.expm1(historical_rates[2]) if history_only else np.nan,historische_vergleichspaare=growth_samples if history_only else 0,markt_tage=sum(flags(d)['markt'] for d in days_of_week(m)),ferien_tage=sum(flags(d)['ferien'] for d in days_of_week(m)),feiertage=sum(flags(d)['feiertag'] for d in days_of_week(m))))
    future=pd.DataFrame(rows)
    future.attrs["anchor_eur"]=anchor
    future.attrs["anchor_kw"]=kwlabel(current)
    future.attrs["anchor_observed_days"]=current_observed_days
    future.attrs["anchor_actual_eur"]=float(current_actual.iloc[0]) if len(current_actual) else None
    return history,future,current,eligible

def seasonal_focus(m):
    if m.month==12: return 'Kaffee/Heißgetränke, warme Backwaren, Schokolade','Zigaretten, Energy-Drinks, Wasser, Snacks'
    if m.month in (1,2):return 'Heißgetränke, Backwaren, Frühstück to go','Zigaretten, Kaffee, Energy-Drinks'
    if m.month in (6,7,8):return 'Wasser gekühlt, Softdrinks, Eistee, Eis','Zigaretten, Energy-Drinks, gekühlte Getränke'
    return 'Kaffee, belegte Backwaren, Snacks für Pendler','Zigaretten, Energy-Drinks, Softdrinks'

