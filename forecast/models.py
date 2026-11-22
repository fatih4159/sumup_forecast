from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import uuid
def defaults():
    return {"horizon":16,"ignore_ff001":True,"history_only":False,"target_enabled":False,"target_value":1500.0,"growth_mode":"Hybrid","assumed_growth":1.5,"saturation_weeks":16,"ceiling_pct":160,"ferien":-12.0,"feiertag":-18.0,"markt":12.0,"pendler":8.0}
class Tenant(models.Model):
    name=models.CharField(max_length=150)
    slug=models.SlugField(unique=True,max_length=175)
    created_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name="created_tenants")
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self):return self.name
class Membership(models.Model):
    ROLE_CHOICES=[("owner","Inhaber"),("admin","Administrator"),("member","Mitglied"),("viewer","Leser")]
    tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,related_name="memberships")
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name="forecast_memberships")
    role=models.CharField(max_length=10,choices=ROLE_CHOICES,default="member")
    class Meta:constraints=[models.UniqueConstraint(fields=["tenant","user"],name="unique_forecast_membership")]
class Settings(models.Model):
    tenant=models.OneToOneField(Tenant,on_delete=models.CASCADE,related_name="forecast_settings")
    values=models.JSONField(default=defaults)
class DataImport(models.Model):
    tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,related_name="imports")
    uploaded_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True)
    name=models.CharField(max_length=255)
    rows=models.PositiveIntegerField()
    accepted_rows=models.PositiveIntegerField(default=0)
    duplicate_rows=models.PositiveIntegerField(default=0)
    uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta:ordering=["-uploaded_at","-id"]

class SaleRow(models.Model):
    tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,related_name="sale_rows")
    fingerprint=models.CharField(max_length=67)
    payload=models.JSONField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["tenant","fingerprint"],name="unique_tenant_sale_row")]
        indexes=[models.Index(fields=["tenant","created_at"],name="forecast_sa_tenant__cbe0a1_idx")]
