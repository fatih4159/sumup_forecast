import io
import pandas as pd
from forecast_engine import load_csv,forecast
from .models import SaleRow,Settings,defaults
from .dedup import row_fingerprint

def tenant_frame(tenant):
    qs=SaleRow.objects.filter(tenant=tenant).order_by("id").values_list("payload",flat=True)
    rows=list(qs)
    if not rows:return None
    return parse_csv_rows(rows)

def parse_csv_rows(rows):
    columns=list(dict.fromkeys(k for row in rows for k in row))
    buffer=io.StringIO()
    pd.DataFrame(rows,columns=columns).to_csv(buffer,index=False)
    buffer.seek(0)
    return load_csv(buffer)

def evaluate(tenant):
    settings,_=Settings.objects.get_or_create(tenant=tenant,defaults={"values":defaults()})
    opts={**defaults(),**settings.values}
    data=tenant_frame(tenant)
    if data is None:return None
    if opts["ignore_ff001"]:
        data=data.loc[~data.ff001_transaction].copy()
    if data.empty:return None
    params={k:float(opts[k]) for k in ("ferien","feiertag","markt","pendler")}
    growth={"mode":opts["growth_mode"],"assumed_growth":float(opts["assumed_growth"]),"saturation_weeks":float(opts["saturation_weeks"]),"ceiling_pct":float(opts["ceiling_pct"])}
    history,future,current,eligible=forecast(data,params,int(opts["horizon"]),growth,history_only=opts["history_only"])
    return history,future,current,eligible,opts

def json_number(v):
    import math
    if v is None:return None
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def series(tenant):
    result=evaluate(tenant)
    if result is None:return None
    h,f,current,eligible,opts=result
    hist=[{"kw":r.kw,"revenue":json_number(r.ist),"days":int(r.days)} for r in h.itertuples()]
    future=[{"kw":r.kw,"base":json_number(r.basis),"moderate":json_number(r.vorsichtig),"optimistic":json_number(r.optimistisch)} for r in f.itertuples()]
    byday=eligible.groupby("day").amount.sum()
    byhour=eligible.groupby(eligible.dt.dt.hour).amount.sum().reindex(range(24),fill_value=0)
    cats=eligible.groupby("Kategorie").amount.sum().sort_values(ascending=False).head(12)
    products=eligible.groupby("Beschreibung").amount.sum().sort_values(ascending=False).head(12)
    return {"history":hist,"future":future,
            "anchor":{"kw":f.attrs["anchor_kw"],"estimate":json_number(f.attrs["anchor_eur"]),"actual":json_number(f.attrs["anchor_actual_eur"]),"observed_days":f.attrs["anchor_observed_days"]},
            "metrics":{"revenue":json_number(eligible.amount.sum()),"average_week":json_number(h.loc[h.days==7,"ist"].mean()),"positions":len(eligible),"next_week":json_number(f.basis.iloc[0])},
            "daily":[{"label":str(k.date()),"value":json_number(v)} for k,v in byday.items()],
            "hours":[{"label":f"{int(k):02d}:00","value":json_number(v)} for k,v in byhour.items()],
            "categories":[{"label":str(k),"value":json_number(v)} for k,v in cats.items()],
            "products":[{"label":str(k),"value":json_number(v)} for k,v in products.items()],
            "settings":opts}
