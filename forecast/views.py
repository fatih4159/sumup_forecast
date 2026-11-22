import csv
import io
import re
from collections import Counter
from uuid import uuid4
from django.contrib import messages
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError,transaction
from django.http import HttpResponse,HttpResponseBadRequest,HttpResponseForbidden
from django.shortcuts import redirect,render,get_object_or_404
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from .context import active_tenant
from .models import Tenant,Membership,Settings,DataImport,SaleRow,defaults
from .dedup import row_fingerprint
from .services import series,evaluate
from forecast_engine import load_csv

def login_view(request):
    if request.user.is_authenticated:return redirect("dashboard")
    if request.method=="POST":
        user=authenticate(request,username=request.POST.get("username",""),password=request.POST.get("password",""))
        if user:
            login(request,user)
            return redirect("dashboard")
        messages.error(request,"Anmeldung fehlgeschlagen.")
    return render(request,"auth.html",{"mode":"login"})

def register_view(request):
    if request.user.is_authenticated:return redirect("dashboard")
    if request.method=="POST":
        username=request.POST.get("username","").strip()
        password=request.POST.get("password","")
        name=request.POST.get("company","").strip()
        try:
            validate_password(password)
            valid_password=True
        except ValidationError as exc:
            valid_password=False
            messages.error(request," ".join(exc.messages))
        if not re.fullmatch(r"[\\w.@+-]{1,150}",username,re.UNICODE):
            messages.error(request,"Ungültiger Benutzername.")
            return render(request,"auth.html",{"mode":"register"})
        if not username or not name or not valid_password:
            messages.error(request,"Bitte gültigen Benutzernamen, Unternehmensnamen und Passwort angeben.")
        elif User.objects.filter(username=username).exists():
            messages.error(request,"Benutzername bereits vergeben.")
        else:
            with transaction.atomic():
                user=User.objects.create_user(username=username,password=password)
                tenant=Tenant.objects.create(name=name,slug=f"{slugify(name)[:60]}-{uuid4().hex[:8]}",created_by=user)
                Membership.objects.create(tenant=tenant,user=user,role="owner")
                Settings.objects.create(tenant=tenant,values=defaults())
            login(request,user)
            request.session["tenant_id"]=tenant.id
            return redirect("dashboard")
    return render(request,"auth.html",{"mode":"register"})

@require_POST
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def dashboard(request):
    if not Membership.objects.filter(user=request.user).exists():return redirect("create_tenant")
    tenant,member,memberships=active_tenant(request)
    result=series(tenant)
    settings,_=Settings.objects.get_or_create(tenant=tenant,defaults={"values":defaults()})
    return render(request,"dashboard.html",{"tenant":tenant,"member":member,"memberships":memberships,"data":result,"settings":{**defaults(),**settings.values},"imports":tenant.imports.all()[:10]})

@login_required
def switch_tenant(request,slug):
    tenant=get_object_or_404(Tenant,slug=slug,memberships__user=request.user)
    request.session["tenant_id"]=tenant.id
    return redirect("dashboard")

@login_required
def create_tenant(request):
    if request.method=="POST":
        name=request.POST.get("name","").strip()
        if not name:return HttpResponseBadRequest("Name fehlt")
        with transaction.atomic():
            tenant=Tenant.objects.create(name=name,slug=f"{slugify(name)[:60]}-{uuid4().hex[:8]}",created_by=request.user)
            Membership.objects.create(tenant=tenant,user=request.user,role="owner")
            Settings.objects.create(tenant=tenant,values=defaults())
        request.session["tenant_id"]=tenant.id
        return redirect("dashboard")
    return render(request,"create_tenant.html")

@require_POST
@login_required
def invite_member(request):
    tenant,member,_=active_tenant(request)
    if member.role not in ("owner","admin"):return HttpResponseForbidden()
    user=User.objects.filter(username=request.POST.get("username","").strip()).first()
    if not user:
        messages.error(request,"Benutzerkonto nicht gefunden.")
    else:
        role=request.POST.get("role","viewer")
        if role not in ("admin","member","viewer"):return HttpResponseBadRequest("Ungültige Rolle")
        Membership.objects.get_or_create(tenant=tenant,user=user,defaults={"role":role})
        messages.success(request,"Mitglied hinzugefügt.")
    return redirect("dashboard")

@require_POST
@login_required
def settings_view(request):
    tenant,member,_=active_tenant(request)
    if member.role not in ("owner","admin"):return HttpResponseForbidden()
    obj,_=Settings.objects.get_or_create(tenant=tenant,defaults={"values":defaults()})
    if request.POST.get("reset")=="1":
        obj.values=defaults()
    else:
        values=defaults()
        values["history_only"]=request.POST.get("history_only")=="on"
        values["ignore_ff001"]=request.POST.get("ignore_ff001")=="on"
        values["target_enabled"]=request.POST.get("target_enabled")=="on"
        numeric={"horizon":(1,104),"target_value":(0,1e12),"assumed_growth":(-8,8),"saturation_weeks":(1,260),"ceiling_pct":(100,10000),"ferien":(-100,200),"feiertag":(-100,200),"markt":(-100,200),"pendler":(-100,200)}
        try:
            for k,(minimum,maximum) in numeric.items():
                number=float(request.POST.get(k,values[k]))
                if not minimum<=number<=maximum:raise ValueError(k)
                values[k]=int(number) if k in ("horizon","saturation_weeks","ceiling_pct") else number
        except ValueError:
            messages.error(request,"Ungültiger Einstellungswert.")
            return redirect("dashboard")
        values["growth_mode"]=request.POST.get("growth_mode","Hybrid")
        if values["growth_mode"] not in ("Hybrid","Annahme","Nur Ist-Trend"):
            return HttpResponseBadRequest("Ungültiger Prognosemodus")
        obj.values=values
    obj.save(update_fields=["values"])
    messages.success(request,"Einstellungen gespeichert.")
    return redirect("dashboard")

@require_POST
@login_required
def import_csv(request):
    tenant,member,_=active_tenant(request)
    if member.role=="viewer":return HttpResponseForbidden()
    uploaded=request.FILES.get("file")
    if not uploaded:return HttpResponseBadRequest("CSV fehlt")
    if uploaded.size>10*1024*1024:return HttpResponseBadRequest("CSV ist größer als 10 MB")
    try:
        raw=uploaded.read()
        text=raw.decode("utf-8-sig")
        parsed=list(csv.DictReader(io.StringIO(text)))
        if not parsed:raise ValueError("Leere CSV")
        checked=load_csv(io.StringIO(text))
        if len(parsed)!=len(checked):raise ValueError("Ungültige Zeilen")
    except (UnicodeError,ValueError,csv.Error,KeyError,TypeError) as exc:
        messages.error(request,f"Import fehlgeschlagen: {exc}")
        return redirect("dashboard")
    with transaction.atomic():
        # Lock the tenant row to serialize concurrent imports of the same tenant.
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        existing=set(SaleRow.objects.filter(tenant=tenant).values_list("fingerprint",flat=True))
        occurrences=Counter()
        accepted=[]
        for row in parsed:
            fingerprint=row_fingerprint(row)
            occurrences[fingerprint]+=1
            key=f"{fingerprint}:{occurrences[fingerprint]}"
            if key not in existing:
                accepted.append(SaleRow(tenant=tenant,fingerprint=key,payload=row))
                existing.add(key)
        SaleRow.objects.bulk_create(accepted,batch_size=500)
        imp=DataImport.objects.create(tenant=tenant,uploaded_by=request.user,name=uploaded.name[:255],rows=len(parsed),accepted_rows=len(accepted),duplicate_rows=len(parsed)-len(accepted))
    messages.success(request,f"Import: {len(accepted)} neue Positionen, {len(parsed)-len(accepted)} Dubletten automatisch ausgeschlossen.")
    return redirect("dashboard")

@login_required
def export_excel(request):
    tenant,_,_=active_tenant(request)
    result=evaluate(tenant)
    if result is None:return HttpResponseBadRequest("Keine Verkaufsdaten vorhanden")
    h,f,_,eligible,opts=result
    output=io.BytesIO()
    import pandas as pd
    with pd.ExcelWriter(output,engine="openpyxl") as writer:
        h.to_excel(writer,sheet_name="Historische KW",index=False)
        f.to_excel(writer,sheet_name="KW-Prognose",index=False)
        eligible.groupby(["Beschreibung","Kategorie"],as_index=False).agg(Umsatz_EUR=("amount","sum"),Menge=("qty","sum")).to_excel(writer,sheet_name="Artikel",index=False)
        pd.DataFrame([opts]).to_excel(writer,sheet_name="Einstellungen",index=False)
    response=HttpResponse(output.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"]='attachment; filename="ForeCast_Prognose.xlsx"'
    return response
