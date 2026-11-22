import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE","webapp.settings")
from django.core.asgi import get_asgi_application
django_app=get_asgi_application()
from fastapi import FastAPI
from forecast.api import router
from starlette.routing import Mount
api=FastAPI(title="ForeCast API",docs_url=None,redoc_url=None,openapi_url=None)
api.include_router(router)
from starlette.applications import Starlette
application=Starlette(routes=[Mount("/api",app=api),Mount("/",app=django_app)])
