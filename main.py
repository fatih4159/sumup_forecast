from __future__ import annotations
import sys, calendar
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QPushButton,QFileDialog,QLabel,QSpinBox,QDoubleSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QMessageBox,QGroupBox,QScrollArea,QCheckBox,QComboBox,QStackedWidget,QFrame,QSizePolicy,QHeaderView,QAbstractItemView,QSplitter,QGraphicsDropShadowEffect,QToolButton)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

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

class Plot(FigureCanvasQTAgg):
    """Point inspection, wheel zoom, left-drag pan and independent axis scaling."""
    def __init__(self):
        self.fig=Figure(figsize=(9,4),facecolor='#FFFFFF',layout='constrained')
        self.ax=self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setMinimumHeight(290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self._series=[];self._labels=[];self._annotation=None
        self._selected_line=None;self._selected_index=None
        self._drag=None;self._dragged=False;self._mode='auto'
        self._initial_limits=None;self._default_scale='linear'
        self._chart_type='line';self._focus='all';self._scale_selector=None
        self.mpl_connect('button_press_event',self._press)
        self.mpl_connect('button_release_event',self._release)
        self.mpl_connect('motion_notify_event',self._motion)
        self.mpl_connect('scroll_event',self._scroll)

    def _bounds(self):
        return self.ax.get_xlim(),self.ax.get_ylim()

    def reset_view(self):
        if self._initial_limits:
            self.ax.set_xlim(*self._initial_limits[0])
            self.ax.set_ylim(*self._initial_limits[1])
            self.draw_idle()

    def set_focus(self, mode):
        self._focus=mode
        self._apply_visibility()
        self.set_scale(self._mode)

    def _apply_visibility(self):
        for line in self.ax.lines:
            label=line.get_label()
            if self._focus=='baseline' and label=='Optimistisch':
                line.set_visible(False)
            else:
                line.set_visible(True)
        # Rebuild legend so its entries correspond to visible series.
        legend=self.ax.get_legend()
        if legend is not None:legend.remove()
        handles,labels=self.ax.get_legend_handles_labels()
        def artist_is_visible(handle):
            # Matplotlib BarContainer is not an Artist and has no get_visible().
            # Its child Rectangle patches carry the actual visibility state.
            if hasattr(handle, 'get_visible'):
                return bool(handle.get_visible())
            patches=getattr(handle, 'patches',None)
            if patches is not None:
                return any(patch.get_visible() for patch in patches)
            return True
        visible=[(h,l) for h,l in zip(handles,labels)
                 if artist_is_visible(h) and not l.startswith('_')]
        if visible:
            self.ax.legend(*zip(*visible),loc='upper left',frameon=False,ncol=2,fontsize=9)

    def _visible_values(self):
        values=[]
        for label,series,color in self._series:
            if self._focus=='baseline' and label=='Optimistisch':continue
            values.extend(float(x) for x in series if np.isfinite(x))
        return np.asarray(values,dtype=float)

    def set_scale(self,mode):
        """Reset all axis limits in the NEW coordinate system; never reuse stale zoom."""
        self._mode=mode
        values=self._visible_values()
        if not len(values):
            self.ax.set_yscale('linear')
            self.ax.set_xlim(-.5,max(.5,len(self._labels)-.5))
            self.ax.set_ylim(0,1)
            self._initial_limits=self._bounds();self.draw_idle();return
        positive=values[values>0]
        ratio=(float(positive.max()/positive.min()) if len(positive)>1 else 1.)
        # Prefer an understandable linear Euro scale. Symlog only if needed.
        scale=('symlog' if ratio>15 else 'linear') if mode=='auto' else ('symlog' if mode=='log' else 'linear')
        if scale=='symlog':
            # Fixed linear threshold at the typical level, not 100 EUR: prevents
            # dozens of irrelevant decades and makes close scenarios separable.
            typical=float(np.median(positive)) if len(positive) else 1.
            linthresh=max(1.,typical*.5)
            self.ax.set_yscale('symlog',linthresh=linthresh,linscale=1)
        else:
            self.ax.set_yscale('linear')
        lo=float(np.min(values));hi=float(np.max(values))
        if hi<=lo:
            pad=max(1.,abs(hi)*.1);lo-=pad;hi+=pad
        else:
            transform=self.ax.yaxis.get_transform()
            tlo,thi=transform.transform([lo,hi]);span=max(1e-9,thi-tlo)
            lo,hi=map(float,transform.inverted().transform([tlo-span*.07,thi+span*.12]))
        # Clamp lower bound at zero for nonnegative Euro amounts.
        if np.min(values)>=0:lo=max(0.,lo)
        self.ax.set_ylim(lo,hi)
        self.ax.set_xlim(-.5,max(.5,len(self._labels)-.5))
        self._initial_limits=self._bounds()
        if scale=='linear':
            self.ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'.replace(',','.')))
        else:
            self.ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'.replace(',','.')))
        self.draw_idle()

    def zoom(self,scale=.8,axis='both',cx=None,cy=None):
        if not self._labels:return
        (xmin,xmax),(ymin,ymax)=self._bounds()
        if cx is None:cx=(xmin+xmax)/2
        if cy is None:cy=(ymin+ymax)/2
        if axis in ('both','x'):
            self.ax.set_xlim(cx+(xmin-cx)*scale,cx+(xmax-cx)*scale)
        if axis in ('both','y'):
            # Transform-space zoom also works for symlog scales.
            transform=self.ax.yaxis.get_transform()
            y0,y1=transform.transform([ymin,ymax])
            center=transform.transform([cy])[0]
            yy=transform.inverted().transform([center+(y0-center)*scale,center+(y1-center)*scale])
            self.ax.set_ylim(*yy)
        self.draw_idle()

    def _scroll(self,event):
        if event.inaxes is not self.ax:return
        key=(event.key or '').lower()
        axis='x' if 'shift' in key else ('y' if 'control' in key or 'ctrl' in key else 'both')
        self.zoom(.8 if event.button=='up' else 1.25,axis,event.xdata,event.ydata)

    def _press(self,event):
        if event.inaxes is not self.ax:return
        if event.button==1:
            self._drag=(event.x,event.y,self._bounds())
            self._dragged=False

    def _motion(self,event):
        if self._drag is None or event.x is None or event.y is None:return
        sx,sy,limits=self._drag
        if not self._dragged and abs(event.x-sx)+abs(event.y-sy)<6:return
        self._dragged=True
        (xmin,xmax),(ymin,ymax)=limits
        # Pan in pixel-relative axis space; stable even during repeated motion events.
        bbox=self.ax.bbox
        dx=(event.x-sx)/max(1.,bbox.width)
        dy=(event.y-sy)/max(1.,bbox.height)
        xrange=xmax-xmin
        self.ax.set_xlim(xmin-dx*xrange,xmax-dx*xrange)
        transform=self.ax.yaxis.get_transform()
        tmin,tmax=transform.transform([ymin,ymax])
        shift=dy*(tmax-tmin)
        shifted=transform.inverted().transform([tmin-shift,tmax-shift])
        self.ax.set_ylim(*shifted)
        self.draw_idle()

    def _release(self,event):
        dragged=self._dragged
        self._drag=None;self._dragged=False
        if not dragged and event.button==1 and event.inaxes is self.ax:
            self._select(event)

    def _select(self,event):
        if not self._series:return
        if self._chart_type=='bar' and event.xdata is not None:
            index=int(round(event.xdata))
            if 0<=index<len(self._labels) and abs(event.xdata-index)<=.45:
                for label,values,color in self._series:
                    if index<len(values) and np.isfinite(values[index]):
                        self._show_point(index,label,values[index],color)
                        return

        nearest=None
        for label,values,color in self._series:
            if self._focus=='baseline' and label=='Optimistisch':continue
            for i,value in enumerate(values):
                if not np.isfinite(value):continue
                px,py=self.ax.transData.transform((i,value))
                distance=np.hypot(event.x-px,event.y-py)
                if nearest is None or distance<nearest[0]:
                    nearest=(distance,i,label,value,color)
        if nearest and nearest[0]<=35:
            _,i,label,value,color=nearest
            self._show_point(i,label,value,color)

    def _show_point(self,i,label,value,color):
        if self._annotation is not None:self._annotation.remove()
        if self._selected_line is not None:self._selected_line.remove()
        self._selected_line=self.ax.axvline(i,color='#64748B',linestyle=':',linewidth=1.2,alpha=.8,zorder=7)
        lines=[str(self._labels[i]),'']
        for name,values,_ in self._series:
            if self._focus=='baseline' and name=='Optimistisch':continue
            if i<len(values) and np.isfinite(values[i]):
                formatted=f'{values[i]:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
                lines.append(f'{name}: {formatted}')
        self._annotation=self.ax.annotate(
            '\\n'.join(lines),xy=(i,value),xytext=(16,20),textcoords='offset points',
            ha='left',va='bottom',fontsize=9,color='#0F172A',zorder=20,
            bbox=dict(boxstyle='round,pad=.65',fc='white',ec='#CBD5E1',alpha=.97),
            arrowprops=dict(arrowstyle='->',color=color,lw=1.4),annotation_clip=False)
        self._selected_index=i
        self.draw_idle()

    def render(self,series,title,vertical=None,percent=False,target=None,chart_type='line'):
        self._chart_type=chart_type
        a=self.ax;a.clear();a.set_facecolor('#FFFFFF')
        self._annotation=None;self._selected_line=None;self._selected_index=None
        self._series=[];self._labels=list(series[0][1]) if series else []
        colors=['#2563EB','#0F766E','#D97706','#8B5CF6']
        for i,(label,xx,yy) in enumerate(series):
            values=np.asarray(yy,dtype=float)
            color=colors[i%len(colors)]
            self._series.append((label,values,color))
            if chart_type=='bar':
                a.bar(np.arange(len(values)),values,color=color,width=.72,label=label,zorder=3)
            else:
                a.plot(np.arange(len(values)),values,color=color,marker='o' if len(values)<30 else None,
                       markersize=3,label=label,linewidth=3.2 if label=='Basis' else 2.3,solid_capstyle='round')
        if target is not None and target>0:
            a.axhline(float(target),color='#DC2626',linestyle=(0,(7,4)),linewidth=2.1,
                      label=f'Umsatzziel: {target:,.0f} €/KW'.replace(',','.'),zorder=5)
            self._series.append(('Umsatzziel',np.full(len(self._labels),float(target)),'#DC2626'))
        if vertical is not None and vertical in self._labels:
            a.axvline(self._labels.index(vertical),color='#E11D48',linestyle='--',linewidth=1.8,label='Aktuelle KW')
        a.set_title(title,loc='left',fontsize=13,fontweight='bold',color='#0F172A',pad=20)
        a.grid(axis='y',alpha=.17);a.spines[['top','right','left']].set_visible(False)
        a.tick_params(axis='both',colors='#64748B',length=0,labelsize=9)
        a.legend(loc='upper left',frameon=False,ncol=2,fontsize=9)
        if not percent:a.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'.replace(',','.')))
        if self._labels:
            step=max(1,len(self._labels)//10) if len(self._labels)>15 else 1
            indices=list(range(0,len(self._labels),step))
            a.set_xticks(indices)
            a.set_xticklabels([str(self._labels[i]) for i in indices],rotation=30 if len(self._labels)>15 else 25,ha='right')
        # Automatically compress extreme scenario spreads, keeping all three lines visible.
        positive=[float(v) for _,vals,_ in self._series for v in vals if np.isfinite(v) and v>0]
        self._default_scale='linear' if chart_type=='bar' else ('symlog' if positive and max(positive)/max(min(positive),1)>12 else 'linear')
        self._apply_visibility()
        self.set_scale(self._mode)
        self.setToolTip('Klicken: Werte | Mausrad: Zoom | Shift+Rad: horizontal | Strg+Rad: vertikal | Ziehen: verschieben')
        self.draw_idle()


def chart_controls(plot):
    bar=QWidget()
    layout=QHBoxLayout(bar);layout.setContentsMargins(0,0,0,0);layout.setSpacing(7)
    hint=QLabel('Mausrad: Zoom  ·  Shift: X  ·  Strg: Y  ·  Ziehen: verschieben')
    hint.setObjectName('infoLabel')
    layout.addWidget(hint);layout.addStretch(1)
    for title,callback in [
        ('＋',lambda:plot.zoom(.8)),('－',lambda:plot.zoom(1.25)),
        ('Zurücksetzen',plot.reset_view)]:
        btn=QPushButton(title);btn.setObjectName('secondaryButton')
        btn.setToolTip('Diagrammansicht ändern');btn.clicked.connect(callback)
        layout.addWidget(btn)
    scale=QComboBox()
    scale.addItems(['Automatische Skalierung','Linear','Komprimiert (Symlog)'])
    scale.currentIndexChanged.connect(lambda i:plot.set_scale(['auto','linear','log'][i]))
    scale.setToolTip('Komprimierte Skalierung zeigt stark abweichende Szenarien gleichzeitig')
    layout.addWidget(scale)
    focus=QComboBox()
    focus.addItems(['Alle Szenarien','Fokus: Basis & Moderat'])
    focus.setToolTip('Blendet das extreme optimistische Szenario aus, ohne Prognosedaten zu ändern')
    focus.currentIndexChanged.connect(lambda i:plot.set_focus('baseline' if i==1 else 'all'))
    layout.addWidget(focus)
    return bar

class MetricCard(QFrame):
    def __init__(self,caption):
        super().__init__();self.setObjectName('metricCard')
        lay=QVBoxLayout(self);lay.setContentsMargins(20,18,20,18);lay.setSpacing(7)
        self.caption=QLabel(caption);self.caption.setObjectName('metricCaption')
        self.value=QLabel('—');self.value.setObjectName('metricValue')
        lay.addWidget(self.caption);lay.addWidget(self.value)
    def set_value(self,value):self.value.setText(str(value))

def section_label(text):
    l=QLabel(text);l.setObjectName('sectionTitle');return l

def card_layout():
    frame=QFrame();frame.setObjectName('contentCard');layout=QVBoxLayout(frame)
    layout.setContentsMargins(22,20,22,20);layout.setSpacing(14)
    return frame,layout


STYLE = """
QWidget#root {background:#F3F6FB;color:#0F172A;font-family:'Inter','Segoe UI','Arial';font-size:13px;}
QWidget#mainArea {background:#F3F6FB;}
QFrame#sidebar {background:#111C32;}
QLabel#brand {color:#FFFFFF;font-size:22px;font-weight:800;letter-spacing:1px;}
QLabel#brandSub {color:#94A3B8;font-size:10px;font-weight:700;letter-spacing:1.6px;}
QLabel#sidebarFoot {color:#8190A9;font-size:11px;line-height:1.5;}
QPushButton#navButton {text-align:left;background:transparent;color:#BAC7D9;border:0;border-radius:9px;padding:13px 14px;font-size:13px;font-weight:550;}
QPushButton#navButton:hover {background:#1D2D49;color:#FFFFFF;}
QPushButton#navButton:checked {background:#29446D;color:#FFFFFF;border-left:3px solid #60A5FA;font-weight:700;}
QLabel#pageTitle {font-size:26px;font-weight:800;color:#0F172A;}
QLabel#pageDesc {color:#64748B;font-size:12px;}
QLabel#fileChip {background:#E8EEF8;color:#334155;padding:10px;border-radius:8px;}
QPushButton#primaryButton {background:#2563EB;color:white;border:0;border-radius:9px;padding:12px 17px;font-weight:700;}
QPushButton#primaryButton:hover {background:#1D4ED8;}
QPushButton#secondaryButton {background:white;color:#1E40AF;border:1px solid #CBD5E1;border-radius:9px;padding:11px 16px;font-weight:700;}
QPushButton#secondaryButton:hover {background:#EFF6FF;}
QPushButton:disabled {background:#E2E8F0;color:#94A3B8;border-color:#E2E8F0;}
QFrame#contentCard,QFrame#metricCard {background:#FFFFFF;border:1px solid #E2E8F0;border-radius:13px;}
QLabel#metricCaption {color:#64748B;font-size:12px;font-weight:550;}
QLabel#metricValue {color:#0F172A;font-size:25px;font-weight:800;}
QLabel#sectionTitle {color:#17243D;font-size:16px;font-weight:750;}
QLabel#infoLabel {color:#64748B;font-size:12px;padding:5px 1px;}
QTableWidget {background:#FFFFFF;border:0;alternate-background-color:#F8FAFC;color:#1E293B;selection-background-color:#DBEAFE;selection-color:#1E3A8A;}
QHeaderView::section {background:#EFF3F9;color:#475569;font-size:11px;font-weight:700;padding:10px;border:0;border-bottom:1px solid #DDE5F0;}
QTableWidget::item {padding:5px;}
QTabWidget::pane {border:0;}
QTabBar::tab {padding:12px 17px;color:#64748B;background:transparent;border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#1D4ED8;border-bottom:2px solid #2563EB;font-weight:700;}
QSpinBox,QDoubleSpinBox,QComboBox {background:#FFFFFF;color:#0F172A;border:1px solid #CBD5E1;border-radius:7px;padding:8px;min-height:20px;min-width:120px;}
QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus {border-color:#2563EB;}
QCheckBox {color:#334155;spacing:9px;font-weight:600;}
QScrollArea {background:transparent;border:0;}
"""

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ForeCast · Verkaufsanalyse')
        self.resize(1510,940);self.setMinimumSize(1050,690)
        self.df=None;self.history=None;self.future=None;self.eligible=None
        self.settings=QSettings('Floesser Laedle','Forecast')
        self.setStyleSheet(STYLE)
        central=QWidget();central.setObjectName('root');self.setCentralWidget(central)
        outer=QHBoxLayout(central);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(246)
        nav=QVBoxLayout(sidebar);nav.setContentsMargins(18,28,18,18);nav.setSpacing(7)
        brand=QLabel('◈  ForeCast');brand.setObjectName('brand');nav.addWidget(brand)
        sub=QLabel('FORECAST  /  ANALYTICS');sub.setObjectName('brandSub');nav.addWidget(sub)
        nav.addSpacing(33)
        self.nav_buttons=[]
        for name in ['Übersicht','KW-Prognose','Verkaufsanalyse','Sortiment','Öffnungszeiten','Modell & Faktoren']:
            button=QPushButton(name);button.setObjectName('navButton');button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            idx=len(self.nav_buttons);button.clicked.connect(lambda _,i=idx:self.navigate(i))
            nav.addWidget(button);self.nav_buttons.append(button)
        nav.addStretch()
        foot=QLabel('LOKAL · KEINE CLOUD\nAlle Berechnungen auf diesem Gerät')
        foot.setObjectName('sidebarFoot');foot.setWordWrap(True);nav.addWidget(foot)
        outer.addWidget(sidebar)
        main=QWidget();main.setObjectName('mainArea');ml=QVBoxLayout(main)
        ml.setContentsMargins(30,23,30,17);ml.setSpacing(18)
        header=QHBoxLayout();header.setSpacing(12)
        header_text=QVBoxLayout();header_text.setSpacing(3)
        self.page_title=QLabel('Übersicht');self.page_title.setObjectName('pageTitle')
        self.page_desc=QLabel('Verkaufsdaten und Prognosen auf einen Blick');self.page_desc.setObjectName('pageDesc')
        header_text.addWidget(self.page_title);header_text.addWidget(self.page_desc)
        header.addLayout(header_text,1)
        self.file_label=QLabel('Noch kein Bericht geladen');self.file_label.setObjectName('fileChip')
        self.file_label.setMaximumWidth(230);header.addWidget(self.file_label)
        self.open_btn=QPushButton('CSV importieren');self.open_btn.setObjectName('primaryButton')
        self.open_btn.clicked.connect(self.open_csv);header.addWidget(self.open_btn)
        self.export_btn=QPushButton('Excel exportieren');self.export_btn.setObjectName('secondaryButton')
        self.export_btn.clicked.connect(self.export);self.export_btn.setEnabled(False);header.addWidget(self.export_btn)
        ml.addLayout(header)
        self.stack=QStackedWidget();ml.addWidget(self.stack,1)
        self.plots={}
        self.metrics={}
        self.make_overview()
        self.make_chart_page('kw','Umsatzentwicklung nach Kalenderwoche','Ist-Werte, drei Prognosepfade und aktuelle KW')
        self.make_analysis()
        self.make_products()
        self.make_schedule()
        self.make_settings()
        outer.addWidget(main,1)
        self.navigate(0)
        self.statusBar().setStyleSheet('QStatusBar {background:#FFFFFF;color:#64748B;border-top:1px solid #E2E8F0;padding-left:12px;}')
        self.statusBar().showMessage('CSV importieren, um die Analyse zu starten.')
        QTimer.singleShot(0,self.restore_settings)

    def make_overview(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0);v.setSpacing(17)
        cards=QHBoxLayout();cards.setSpacing(14)
        for key,title in [('revenue','Artikelumsatz (Ist)'),('weekly','Ø Umsatz / vollständige KW'),('transactions','Berücksichtigte Positionen'),('next','Prognose nächste KW')]:
            card=MetricCard(title);self.metrics[key]=card;cards.addWidget(card)
        v.addLayout(cards)
        frame,content=card_layout();content.addWidget(section_label('Umsatztrend · Ist und Prognose'))
        self.plots['overview']=Plot();content.addWidget(chart_controls(self.plots['overview']));content.addWidget(self.plots['overview'],1)
        v.addWidget(frame,1)
        self.overview_note=QLabel('Lade einen SumUp-Verkaufsbericht, um deine Entwicklung zu sehen.')
        self.overview_note.setObjectName('infoLabel');self.overview_note.setWordWrap(True)
        v.addWidget(self.overview_note)
        self.stack.addWidget(page)

    def make_chart_page(self,key,title,subtitle):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0);v.setSpacing(16)
        frame,content=card_layout();content.addWidget(section_label(title))
        self.plots[key]=Plot();content.addWidget(chart_controls(self.plots[key]));content.addWidget(self.plots[key],1);v.addWidget(frame,3)
        frame2,content2=card_layout();content2.addWidget(section_label('KW-Daten im Detail'))
        self.table=QTableWidget();self.prepare_table(self.table);content2.addWidget(self.table)
        v.addWidget(frame2,2);self.stack.addWidget(page)

    def make_analysis(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0);v.setSpacing(15)
        self.analysis_tabs=QTabWidget();self.analysis_tabs.setObjectName('analysisTabs')
        for key,name in [('daily','Tagesverlauf'),('hours','Stundenverlauf'),('categories','Kategorien'),('items','Topartikel')]:
            widget=QWidget();lay=QVBoxLayout(widget);lay.setContentsMargins(0,16,0,0)
            frame,content=card_layout();self.plots[key]=Plot();content.addWidget(chart_controls(self.plots[key]));content.addWidget(self.plots[key]);lay.addWidget(frame)
            self.analysis_tabs.addTab(widget,name)
        v.addWidget(self.analysis_tabs);self.stack.addWidget(page)

    def make_products(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        frame,content=card_layout();content.addWidget(section_label('Artikel · Absatz und Zielbestand'))
        info=QLabel('Zielbestände sind Richtwerte. Für echte Bestellvorschläge wird ein aktueller Lagerbestand benötigt.')
        info.setObjectName('infoLabel');info.setWordWrap(True);content.addWidget(info)
        self.products=QTableWidget();self.prepare_table(self.products);content.addWidget(self.products)
        v.addWidget(frame);self.stack.addWidget(page)

    def make_schedule(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0);v.setSpacing(16)
        frame,content=card_layout();content.addWidget(section_label('Öffnungszeiten · datenbasierte Testfenster'))
        self.schedule=QTableWidget();self.prepare_table(self.schedule);content.addWidget(self.schedule)
        v.addWidget(frame,1)
        hint=QLabel('Öffnungszeiten sind Testszenarien: Kassenbuchungen außerhalb bisheriger Öffnungszeiten fehlen. Sonntagsöffnung ist gesondert rechtlich zu prüfen.')
        hint.setObjectName('infoLabel');hint.setWordWrap(True);v.addWidget(hint)
        self.stack.addWidget(page)

    def make_settings(self):
        page=QScrollArea();page.setWidgetResizable(True);page.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();v=QVBoxLayout(body);v.setContentsMargins(0,0,8,0);v.setSpacing(16)
        f,layout=card_layout();layout.addWidget(section_label('Prognosezeitraum & Datenfilter'))
        form=QFormLayout();form.setSpacing(12)
        self.horizon=QSpinBox();self.horizon.setRange(4,104);self.horizon.setValue(16)
        form.addRow('Zukünftige Kalenderwochen',self.horizon);layout.addLayout(form)
        self.ignore_ff001=QCheckBox('Privatkäufe mit FF001 vollständig ausschließen')
        self.ignore_ff001.setChecked(True)
        self.ignore_ff001.setToolTip('Schließt alle Positionen derselben Transaktionsnummer aus.')
        self.ignore_ff001.toggled.connect(self.calculate)
        layout.addWidget(self.ignore_ff001)
        self.ff001_label=QLabel('FF001: Noch keine Daten geladen');self.ff001_label.setObjectName('infoLabel')
        layout.addWidget(self.ff001_label);v.addWidget(f)
        f,layout=card_layout();layout.addWidget(section_label('Wachstum & Anlaufphase'))
        form=QFormLayout();form.setSpacing(12)
        self.growth_mode=QComboBox();self.growth_mode.addItems(['Hybrid','Annahme','Nur Ist-Trend'])
        form.addRow('Trendquelle',self.growth_mode)
        self.assumed_growth=QDoubleSpinBox();self.assumed_growth.setRange(-5,8);self.assumed_growth.setDecimals(1)
        self.assumed_growth.setSingleStep(.5);self.assumed_growth.setValue(1.5);self.assumed_growth.setSuffix(' %/KW')
        form.addRow('Anlaufwachstum',self.assumed_growth)
        self.saturation=QSpinBox();self.saturation.setRange(2,104);self.saturation.setValue(16)
        form.addRow('Sättigungsdauer (KW)',self.saturation)
        self.ceiling=QSpinBox();self.ceiling.setRange(100,400);self.ceiling.setValue(160);self.ceiling.setSuffix(' %')
        form.addRow('Maximaler relativer Umsatz',self.ceiling)
        layout.addLayout(form)
        self.trend_label=QLabel('Wachstumsmodell: Daten laden');self.trend_label.setObjectName('infoLabel')
        self.trend_label.setWordWrap(True);layout.addWidget(self.trend_label);v.addWidget(f)
        f,layout=card_layout();layout.addWidget(section_label('Prognoseverfahren'))
        self.history_only=QCheckBox('Nur historische Verkaufsdaten verwenden')
        self.history_only.setToolTip('Ignoriert Feiertage, Ferien, Weihnachtsmarkt, Pendler- und angenommene Wachstumsfaktoren. Nutzt ausschließlich historische KW-Umsätze.')
        self.history_only.toggled.connect(self.history_mode_changed)
        layout.addWidget(self.history_only)
        info=QLabel('Aktiv: Prognose nur aus vollständigen historischen KW. Ab 3 vollständigen KW wird ein gemessener Trend geschätzt; sonst wird das beobachtete Niveau fortgeschrieben. Saisonfaktoren und Wachstumsannahmen entfallen.')
        info.setObjectName('infoLabel');info.setWordWrap(True);layout.addWidget(info)
        v.addWidget(f)
        f,layout=card_layout();layout.addWidget(section_label('Optionales Umsatzziel'))
        self.target_enabled=QCheckBox('Umsatzziel aktivieren')
        self.target_enabled.setChecked(False)
        self.target_enabled.setToolTip('Vergleicht die Umsatzentwicklung mit einem konstanten Ziel pro Kalenderwoche.')
        layout.addWidget(self.target_enabled)
        form=QFormLayout();form.setSpacing(12)
        self.target_value=QDoubleSpinBox()
        self.target_value.setRange(0,100000000)
        self.target_value.setDecimals(2)
        self.target_value.setSingleStep(100)
        self.target_value.setValue(1500)
        self.target_value.setSuffix(' €/KW')
        self.target_value.setEnabled(False)
        self.target_enabled.toggled.connect(self.target_value.setEnabled)
        self.target_enabled.toggled.connect(self.target_changed)
        self.target_value.valueChanged.connect(self.target_changed)
        form.addRow('Zielumsatz pro KW',self.target_value)
        layout.addLayout(form)
        note=QLabel('Optionaler Referenzwert: Das Umsatzziel beeinflusst nicht die Prognose, sondern zeigt die Zielerreichung und die Abweichung in EUR und Prozent.')
        note.setObjectName('infoLabel');note.setWordWrap(True);layout.addWidget(note)
        v.addWidget(f)
        f,layout=card_layout();layout.addWidget(section_label('Saisonale Einflussfaktoren'))
        form=QFormLayout();form.setSpacing(12);self.params={}
        for key,title,default in [('ferien','Schulferien Baden-Württemberg',-12),('feiertag','Gesetzliche Feiertage',-18),('markt','Pforzheimer Weihnachtsmarkt',12),('pendler','Werktags-Pendler',8)]:
            spin=QDoubleSpinBox();spin.setRange(-80,200);spin.setSuffix(' %');spin.setValue(default);spin.setDecimals(1)
            self.params[key]=spin;form.addRow(title,spin)
        layout.addLayout(form);v.addWidget(f)
        f,layout=card_layout()
        note=QLabel('Diese Faktoren sind frei anpassbare Annahmen, keine gemessenen Auswirkungen. Die App nutzt keine Live-Frequenzdaten der Bushaltestelle.')
        note.setObjectName('infoLabel');note.setWordWrap(True);layout.addWidget(note)
        apply=QPushButton('Änderungen anwenden & neu berechnen');apply.setObjectName('primaryButton')
        apply.clicked.connect(self.calculate);layout.addWidget(apply);v.addWidget(f)
        v.addStretch();page.setWidget(body);self.stack.addWidget(page)

    def navigate(self,index):
        self.stack.setCurrentIndex(index)
        for i,btn in enumerate(self.nav_buttons):btn.setChecked(i==index)
        names=['Übersicht','KW-Prognose','Verkaufsanalyse','Sortiment','Öffnungszeiten','Modell & Faktoren']
        descriptions=['Dein Geschäft auf einen Blick','Szenarien und KW-Entwicklung','Tages-, Stunden- und Artikelmuster','Schnelldreher und Bestandsrichtwerte','Verkaufsfrequenz und Testzeiten','Prognoseannahmen transparent anpassen']
        self.page_title.setText(names[index]);self.page_desc.setText(descriptions[index])

    def prepare_table(self,table):
        table.setAlternatingRowColors(True);table.setShowGrid(False)
        table.verticalHeader().setVisible(False);table.verticalHeader().setDefaultSectionSize(36)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)

    def restore_settings(self):
        self.history_only.blockSignals(True)
        self.history_only.setChecked(str(self.settings.value('history_only','false')).lower() in ('true','1','yes'))
        self.history_only.blockSignals(False)
        enabled=str(self.settings.value('target_enabled','false')).lower() in ('true','1','yes')
        try: amount=float(self.settings.value('target_value',1500))
        except (TypeError,ValueError): amount=1500.
        self.target_value.blockSignals(True);self.target_enabled.blockSignals(True)
        self.target_value.setValue(max(0.,amount));self.target_enabled.setChecked(enabled)
        self.target_value.setEnabled(enabled)
        self.target_value.blockSignals(False);self.target_enabled.blockSignals(False)
        if self.df is None and self.settings.value('last_csv'):
            path=str(self.settings.value('last_csv'))
            if Path(path).is_file():
                try:self.df=load_csv(path);self.file_label.setText(Path(path).name);self.settings.setValue('last_csv',path);self.calculate()
                except Exception:self.df=None

    def open_csv(self):
        path,_=QFileDialog.getOpenFileName(self,'SumUp CSV öffnen','','CSV-Dateien (*.csv);;Alle Dateien (*)')
        if not path:return
        try:self.df=load_csv(path);self.file_label.setText(Path(path).name);self.settings.setValue('last_csv',path);self.calculate()
        except Exception as e:QMessageBox.critical(self,'CSV-Fehler',str(e))
    def history_mode_changed(self,checked):
        self.settings.setValue('history_only',checked)
        self.calculate()

    def target_changed(self,*args):
        self.settings.setValue('target_enabled',self.target_enabled.isChecked())
        self.settings.setValue('target_value',self.target_value.value())
        self.calculate()

    def active_target(self):
        return self.target_value.value() if self.target_enabled.isChecked() and self.target_value.value()>0 else None

    def params_values(self):return {k:v.value() for k,v in self.params.items()}
    def growth_values(self):
        return {'mode':self.growth_mode.currentText(),
                'assumed_growth':self.assumed_growth.value(),
                'saturation_weeks':self.saturation.value(),
                'ceiling_pct':self.ceiling.value()}
    def fill_table(self,table,headers,rows):
        table.setRowCount(len(rows));table.setColumnCount(len(headers));table.setHorizontalHeaderLabels(headers)
        for i,row in enumerate(rows):
            for j,val in enumerate(row):
                item=QTableWidgetItem(str(val));item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);table.setItem(i,j,item)
        table.resizeColumnsToContents();table.setAlternatingRowColors(True)
    def calculate(self):
        if self.df is None:return
        try:
            excluded_ff=self.df[self.df.ff001_transaction]
            working=self.df[~self.df.ff001_transaction].copy() if self.ignore_ff001.isChecked() else self.df.copy()
            count=excluded_ff['Transaktionsnummer'].replace('',pd.NA).nunique() if 'Transaktionsnummer' in excluded_ff else len(excluded_ff)
            self.ff001_label.setText(f'FF001: {count} Transaktionen, {len(excluded_ff)} Positionen, {excluded_ff.amount.sum():.2f} €' + (' ausgeschlossen' if self.ignore_ff001.isChecked() else ' enthalten'))
            if working.empty: raise ValueError('Nach dem FF001-Filter sind keine Verkaufspositionen vorhanden.')
            h,f,current,eligible=forecast(working,self.params_values(),self.horizon.value(),self.growth_values(),history_only=self.history_only.isChecked())
            self.history,self.future,self.current,self.eligible=h,f,current,eligible
            self.export_btn.setEnabled(True)
            nfull=int((h.days==7).sum())
            if self.history_only.isChecked():
                r=f.iloc[0]
                self.trend_label.setText(f'Historische KW-Veränderungen ({int(r.historische_vergleichspaare)} Vergleiche): Basis {r.historisch_basis_pct:+.2f} %, Moderat {r.historisch_vorsichtig_pct:+.2f} %, Optimistisch {r.historisch_optimistisch_pct:+.2f} % je KW. Bei kurzer Historie sehr unsicher.')
            else:
                self.trend_label.setText(f'Saisonmodell | {nfull} vollständige KW | Ist-Trend: {f.trend_ist_pct.iloc[0]:+.2f} %/KW | Modell: {f.trend_modell_pct.iloc[0]:+.2f} %/KW.')
            x=[kwlabel(d) for d in list(h.monday)+list(f.monday)]
            past=[float(v) for v in h.ist]+[np.nan]*len(f)
            # All three lines originate at the estimated FULL CURRENT KW,
            # rather than the incomplete observed amount or a historical median.
            anchor=float(f.attrs['anchor_eur'])
            anchor_idx=x.index(kwlabel(current)) if kwlabel(current) in x else len(h)-1
            fc=[np.nan]*len(x);low=[np.nan]*len(x);high=[np.nan]*len(x)
            for arr,col in ((fc,'basis'),(low,'vorsichtig'),(high,'optimistisch')):
                arr[anchor_idx]=anchor
                for j,value in enumerate(f[col]):arr[len(h)+j]=float(value)
            curves=[('Ist-Umsatz',x,past),('Basis',x,fc),('Moderat',x,low),('Optimistisch',x,high)]
            target=self.active_target()
            if target is not None:
                f['umsatzziel_eur']=target
                f['zielabweichung_eur']=f.basis-target
                f['zielerreichung_pct']=100*f.basis/target
                h['umsatzziel_eur']=target
                h['zielabweichung_eur']=h.ist-target
                h['zielerreichung_pct']=100*h.ist/target
            else:
                for frame in (h,f):
                    frame['umsatzziel_eur']=np.nan
                    frame['zielabweichung_eur']=np.nan
                    frame['zielerreichung_pct']=np.nan
            self.plots['kw'].render(curves,'Umsatz pro Kalenderwoche (EUR)',kwlabel(current),target=target)
            self.plots['overview'].render(curves,'Entwicklung und Szenarien (EUR)',kwlabel(current),target=target)
            self.metrics['revenue'].set_value(f'{eligible.amount.sum():,.2f} €'.replace(',','X').replace('.',',').replace('X','.'))
            full=h[h.days==7]
            self.metrics['weekly'].set_value(f'{full.ist.mean():,.0f} €'.replace(',','.') if len(full) else '—')
            self.metrics['transactions'].set_value(f'{len(working):,}'.replace(',','.'))
            self.metrics['next'].set_value(f'{f.basis.iloc[0]:,.0f} €'.replace(',','.'))
            self.overview_note.setText(f'Anker {kwlabel(current)}: {anchor:,.2f} € (geschätzter Gesamt-KW-Umsatz, {f.attrs["anchor_observed_days"]} beobachtete Tage) · {len(h)} historische KW · {len(full)} vollständige KW · {len(f)} Prognose-KW · FF001-Filter: {"aktiv" if self.ignore_ff001.isChecked() else "inaktiv"}. '+('Keine externen Faktoren oder Wachstumsannahmen.' if self.history_only.isChecked() else 'Saison- und Wachstumsfaktoren sind Modellannahmen.'))
            byday=eligible.groupby('day').amount.sum().sort_index();self.plots['daily'].render([('Artikelumsatz',byday.index.strftime('%d.%m'),byday.values)],'Historischer Tagesumsatz (EUR)',chart_type='bar')
            byhour=eligible.groupby(eligible.dt.dt.hour).amount.sum().reindex(range(24),fill_value=0)
            self.plots['hours'].render([('Umsatz',list(range(24)),byhour.values)],'Umsatz nach Uhrzeit (nur beobachtete Buchungen)',chart_type='bar')
            cats=eligible.groupby('Kategorie').amount.sum().sort_values(ascending=False).head(12)
            self.plots['categories'].render([('Umsatz',cats.index.tolist(),cats.values)],'Top-Kategorien (EUR)',chart_type='bar')
            top=eligible.groupby('Beschreibung').amount.sum().sort_values(ascending=False).head(12)
            self.plots['items'].render([('Umsatz',list(range(1,len(top)+1)),top.values)],'Topartikel nach Umsatz (Rang 1–12)',chart_type='bar')
            rows=[]
            for _,r in h.iterrows():
                rows.append([r.kw,'Ist',f'{r.ist:.2f}', '', '',r.days,'','','',
                             f'{target:.2f}' if target else '—',
                             f'{r.zielabweichung_eur:+.2f}' if target else '—',
                             f'{r.zielerreichung_pct:.1f} %' if target else '—'])
            for _,r in f.iterrows():
                rows.append([r.kw,'Prognose',f'{r.basis:.2f}',f'{r.vorsichtig:.2f}',f'{r.optimistisch:.2f}',7,r.markt_tage,r.ferien_tage,r.feiertage,
                             f'{target:.2f}' if target else '—',
                             f'{r.zielabweichung_eur:+.2f}' if target else '—',
                             f'{r.zielerreichung_pct:.1f} %' if target else '—'])
            self.fill_table(self.table,['KW','Typ','Basis/Ist €','Moderat €','Optimistisch €','Beobachtete Tage','Markttage','Ferientage','Feiertage','Ziel €/KW','Abweichung €','Zielerreichung'],rows)
            item_rows=[]
            n=max(1,(working.dt.max().date()-working.dt.min().date()).days+1)
            grouped=eligible.groupby(['Beschreibung','Kategorie'],dropna=False).agg(umsatz=('amount','sum'),menge=('qty','sum')).sort_values('umsatz',ascending=False).head(100)
            for (name,cat),r in grouped.iterrows():
                weekly=max(0,r.menge*7/n);stock=int(np.ceil(weekly*1.5));item_rows.append([name,cat,f'{r.umsatz:.2f}',f'{r.menge:.0f}',f'{weekly:.1f}',stock,'Zielbestand; Ist-Bestand nicht bekannt'])
            self.fill_table(self.products,['Artikel','Kategorie','Ist-Umsatz €','Ist-Menge','Ø Stück/KW','Zielbestand (1,5 KW)','Hinweis'],item_rows)
            self.fill_table(self.schedule,['Zeitraum','Test-Öffnung','Begründung'],[
                ['Mo–Fr','08:00–20:00','Beobachtete Verkäufe; anpassen an Personalkosten'],['Mo–Fr optional','06:30–08:00','Pendler-Test; Nachfrage bisher nicht belegt'],['Samstag','09:00–20:00','Test; Stundenumsätze prüfen'],['Sonntag','Nur nach Prüfung','Sonntagsöffnung rechtlich prüfen; keine pauschale Empfehlung'],['Weihnachtsmarkt','18:00–21:00 testen','Zusätzliche Frequenz nur als Hypothese']])
            self.statusBar().showMessage(f'{len(working)} berücksichtigte Positionen · {working.amount.sum():,.2f} € saldiert · {len(h)} historische KW · {len(f)} Prognose-KW')
        except Exception as e:QMessageBox.critical(self,'Berechnungsfehler',str(e))
    def export(self):
        if self.df is None or self.future is None:QMessageBox.information(self,'Hinweis','Bitte zuerst eine CSV laden.');return
        path,_=QFileDialog.getSaveFileName(self,'Excel speichern','ForeCast_Prognose.xlsx','Excel (*.xlsx)')
        if not path:return
        try:
            with pd.ExcelWriter(path,engine='openpyxl') as writer:
                self.history.to_excel(writer,sheet_name='Historische KW',index=False)
                self.future.to_excel(writer,sheet_name='KW-Prognose',index=False)
                pd.DataFrame([{'Aktuelle_KW':self.future.attrs['anchor_kw'],
                    'Ist_bisher_EUR':self.future.attrs['anchor_actual_eur'],
                    'Prognostizierter_Gesamtumsatz_aktuelle_KW_EUR':self.future.attrs['anchor_eur'],
                    'Beobachtete_Tage':self.future.attrs['anchor_observed_days'],
                    'Methode':'Ist-Umsatz + fehlende Wochentage aus historischen gleichen Wochentagen; keine externen Faktoren im Historikmodus'}]).to_excel(writer,sheet_name='Prognose-Anker',index=False)
                pd.DataFrame([{'Modus':'Nur historische Verkaufsdaten' if self.history_only.isChecked() else 'Mit externen Faktoren',
                    'Externe_Faktoren_verwendet':not self.history_only.isChecked(),
                    'Wachstumsannahmen_verwendet':not self.history_only.isChecked(),
                    'Historische_vollständige_KW':int((self.history.days==7).sum()),
                    'Hinweis':'Bei 2 vollständigen KW gedämpfter Ist-Trend; Szenariobreite aus Tagesumsätzen (heuristisch), keine statistisch kalibrierte Sicherheit.'}]).to_excel(writer,sheet_name='Prognoseverfahren',index=False)
                pd.DataFrame([{'Umsatzziel_aktiv':self.active_target() is not None,
                               'Umsatzziel_EUR_pro_KW':self.active_target(),
                               'Bedeutung':'Referenzlinie, verändert die Umsatzprognose nicht'}]).to_excel(writer,sheet_name='Umsatzziel',index=False)
                self.eligible.groupby(['Beschreibung','Kategorie'],as_index=False).agg(Umsatz_EUR=('amount','sum'),Menge=('qty','sum')).sort_values('Umsatz_EUR',ascending=False).to_excel(writer,sheet_name='Artikel',index=False)
                self.eligible.groupby('Kategorie',as_index=False).agg(Umsatz_EUR=('amount','sum'),Menge=('qty','sum')).to_excel(writer,sheet_name='Kategorien',index=False)
                self.eligible.groupby(self.eligible.dt.dt.hour).amount.sum().rename_axis('Stunde').reset_index(name='Umsatz_EUR').to_excel(writer,sheet_name='Stunden',index=False)
                seasonal=pd.DataFrame([{'KW':r.kw,'Fokusartikel':seasonal_focus(r.monday)[0],'Schnelldreher':seasonal_focus(r.monday)[1]} for _,r in self.future.iterrows()]);seasonal.to_excel(writer,sheet_name='Sortimentsplan',index=False)
                pd.DataFrame([{'Parameter':k,'Prozent':v} for k,v in self.params_values().items()]).to_excel(writer,sheet_name='Annahmen',index=False)
                pd.DataFrame([{'Parameter':k,'Wert':v} for k,v in self.growth_values().items()] +
                  [{'Parameter':'Vollständige historische KW','Wert':int((self.history.days==7).sum())},
                   {'Parameter':'Gemessener Wochen-Trend (%)','Wert':float(self.future.trend_ist_pct.iloc[0])},
                   {'Parameter':'Verwendeter Modell-Trend (%)','Wert':float(self.future.trend_modell_pct.iloc[0])},
                   {'Parameter':'Hinweis','Wert':'Wachstum und Saisonfaktoren sind Annahmen; kein garantierter Umsatz.'}]).to_excel(writer,sheet_name='Wachstumsmodell',index=False)
                pd.DataFrame([{'FF001_ignorieren':self.ignore_ff001.isChecked(),'Markierte_Positionen':int(self.df.ff001_transaction.sum()),'Markierter_Umsatz_EUR':float(self.df.loc[self.df.ff001_transaction,'amount'].sum()),'Regel':'Exakter Barcode FF001; gesamte Transaktion ausgeschlossen'}]).to_excel(writer,sheet_name='FF001-Filter',index=False)
                from openpyxl.chart import LineChart,Reference
                from openpyxl.styles import Font,PatternFill
                for ws in writer.book:
                    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                    for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='183153')
                    for col in ws.columns:
                        letter=col[0].column_letter;ws.column_dimensions[letter].width=min(48,max(13,max(len(str(c.value or '')) for c in list(col)[:100])+2))
                for sheet,columns,cat_col,anchor in [('Historische KW',[3,4],2,'P2'),('KW-Prognose',[4,5,6],2,'S2'),('Artikel',[3,4],1,'H2'),('Kategorien',[2,3],1,'G2'),('Stunden',[2],1,'E2')]:
                    ws=writer.book[sheet];chart=LineChart();chart.title=sheet;chart.style=13;chart.width=20;chart.height=10
                    if self.active_target() is not None and sheet in ('Historische KW','KW-Prognose'):
                        header_map={cell.value:cell.column for cell in ws[1]}
                        if 'umsatzziel_eur' in header_map: columns=columns+[header_map['umsatzziel_eur']]
                    for col in columns:
                        if col<=ws.max_column:chart.add_data(Reference(ws,min_col=col,min_row=1,max_row=ws.max_row),titles_from_data=True)
                    chart.set_categories(Reference(ws,min_col=cat_col,min_row=2,max_row=ws.max_row));ws.add_chart(chart,anchor)
            QMessageBox.information(self,'Export erfolgreich',f'Gespeichert:\n{path}')
        except Exception as e:QMessageBox.critical(self,'Exportfehler',str(e))

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setApplicationName('ForeCast');win=Main();win.show()
    if len(sys.argv)>1:
        try:win.df=load_csv(sys.argv[1]);win.file_label.setText(Path(sys.argv[1]).name);win.calculate()
        except Exception as e:QMessageBox.warning(win,'Import',str(e))
    sys.exit(app.exec())
if __name__=='__main__':main()