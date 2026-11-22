from django.contrib import admin
from django.urls import path
from forecast import views
urlpatterns=[
    path("admin/",admin.site.urls),
    path("login/",views.login_view,name="login"),
    path("logout/",views.logout_view,name="logout"),
    path("register/",views.register_view,name="register"),
    path("",views.dashboard,name="dashboard"),
    path("tenant/<slug:slug>/",views.switch_tenant,name="switch_tenant"),
    path("tenant/create/",views.create_tenant,name="create_tenant"),
    path("team/invite/",views.invite_member,name="invite_member"),
    path("settings/",views.settings_view,name="settings"),
    path("import/",views.import_csv,name="import_csv"),
    path("export/",views.export_excel,name="export_excel"),
]
