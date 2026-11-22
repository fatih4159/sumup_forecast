from django.contrib import admin
from .models import Tenant,Membership,Settings,DataImport
admin.site.register(Tenant)
admin.site.register(Membership)
admin.site.register(Settings)
admin.site.register(DataImport)
