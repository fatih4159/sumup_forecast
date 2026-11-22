document.addEventListener("DOMContentLoaded",async()=>{
  let data;
  try{
    const res=await fetch("/api/dashboard",{credentials:"same-origin"});
    if(!res.ok)throw new Error("HTTP "+res.status);
    data=await res.json();
  }catch(e){console.warn("Forecast API unavailable",e);return;}
  if(!data||!data.history)return;
  if(typeof Chart==="undefined"){console.error("Chart.js not loaded");return;}
  const currency=new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"});
  const integer=new Intl.NumberFormat("de-DE");
  for(const [id,value,fmt] of [["mRevenue",data.metrics.revenue,currency],["mWeek",data.metrics.average_week,currency],["mPositions",data.metrics.positions,integer],["mNext",data.metrics.next_week,currency]]){
    document.getElementById(id).textContent=value==null?"—":fmt.format(value);
  }
  const anchor=document.getElementById("anchor");
  anchor.textContent=`Anker ${data.anchor.kw}: ${currency.format(data.anchor.estimate)} (geschätzter Gesamtumsatz der aktuellen KW; ${data.anchor.observed_days} erfasste Tage)`;
  const labels=[...data.history.map(r=>r.kw),...data.future.map(r=>r.kw)];
  const actual=[...data.history.map(r=>r.revenue),...data.future.map(()=>null)];
  const base=labels.map(()=>null),moderate=labels.map(()=>null),optimistic=labels.map(()=>null);
  const index=labels.indexOf(data.anchor.kw);
  if(index>=0){base[index]=moderate[index]=optimistic[index]=data.anchor.estimate;}
  for(let i=0;i<data.future.length;i++){
    const j=data.history.length+i;
    base[j]=data.future[i].base;
    moderate[j]=data.future[i].moderate;
    optimistic[j]=data.future[i].optimistic;
  }
  const zoomSettings={pan:{enabled:true,mode:"xy"},zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:"xy"}};
  function build(id,type,chartLabels,datasets,extra={}){
    const canvas=document.getElementById(id);
    if(!canvas)return;
    new Chart(canvas,{type,data:{labels:chartLabels,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:datasets.length>1},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${currency.format(c.parsed.y||0)}`}}},scales:{y:{beginAtZero:true,ticks:{callback:v=>integer.format(v)}},x:{ticks:{autoSkip:true,maxTicksLimit:16}}},...extra}});
  }
  const line=(label,values,color)=>({label,data:values,borderColor:color,backgroundColor:color,tension:.22,spanGaps:false,pointRadius:2});
  const curveSets=[line("Ist",actual,"#20395b"),line("Basis",base,"#3867e9"),line("Moderat",moderate,"#d9a13c"),line("Optimistisch",optimistic,"#208f76")];
  build("overviewChart","line",labels,curveSets);
  build("forecastChart","line",labels,curveSets);
  for(const [id,key] of [["dailyChart","daily"],["hoursChart","hours"],["categoriesChart","categories"],["productsChart","products"]]){
    const rows=data[key]||[];
    build(id,"bar",rows.map(r=>r.label),[{label:"Umsatz",data:rows.map(r=>r.value),backgroundColor:"#4774ed",borderRadius:4}]);
  }
  const body=document.getElementById("forecastRows");
  for(const r of [...data.history.map(x=>({kw:x.kw,base:x.revenue})),...data.future]){
    const tr=document.createElement("tr");
    for(const v of [r.kw,r.base,r.moderate,r.optimistic]){
      const td=document.createElement("td");
      td.textContent=v==null?"—":typeof v==="number"?currency.format(v):v;
      tr.append(td);
    }
    body.append(tr);
  }
});
