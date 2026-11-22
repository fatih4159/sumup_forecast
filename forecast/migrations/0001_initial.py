# Generated for ForeCast web initial schema.
from django.conf import settings
from django.db import migrations,models
import django.db.models.deletion
import forecast.models

class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name="Tenant",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("name",models.CharField(max_length=150)),
            ("slug",models.SlugField(max_length=175,unique=True)),
            ("created_at",models.DateTimeField(auto_now_add=True)),
            ("created_by",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="created_tenants",to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Membership",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("role",models.CharField(choices=[("owner","Inhaber"),("admin","Administrator"),("member","Mitglied"),("viewer","Leser")],default="member",max_length=10)),
            ("tenant",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="memberships",to="forecast.tenant")),
            ("user",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="forecast_memberships",to=settings.AUTH_USER_MODEL)),
        ],options={"constraints":[models.UniqueConstraint(fields=("tenant","user"),name="unique_forecast_membership")]}),
        migrations.CreateModel(name="Settings",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("values",models.JSONField(default=forecast.models.defaults)),
            ("tenant",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="forecast_settings",to="forecast.tenant")),
        ]),
        migrations.CreateModel(name="DataImport",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("name",models.CharField(max_length=255)),
            ("rows",models.PositiveIntegerField()),
            ("accepted_rows",models.PositiveIntegerField(default=0)),
            ("duplicate_rows",models.PositiveIntegerField(default=0)),
            ("uploaded_at",models.DateTimeField(auto_now_add=True)),
            ("tenant",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="imports",to="forecast.tenant")),
            ("uploaded_by",models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
        ],options={"ordering":["-uploaded_at","-id"]}),
        migrations.CreateModel(name="SaleRow",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("fingerprint",models.CharField(max_length=67)),
            ("payload",models.JSONField()),
            ("created_at",models.DateTimeField(auto_now_add=True)),
            ("tenant",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="sale_rows",to="forecast.tenant")),
        ],options={"indexes":[models.Index(fields=["tenant","created_at"],name="forecast_sa_tenant__cbe0a1_idx")],"constraints":[models.UniqueConstraint(fields=("tenant","fingerprint"),name="unique_tenant_sale_row")]}),
    ]
