from fastapi import APIRouter,HTTPException,Request
from asgiref.sync import sync_to_async
router=APIRouter()

@router.get("/health")
def health():
    return {"status":"ok"}

def _read(request):
        from .services import series
    # Django sessions do not propagate through the mounted FastAPI ASGI application.
    # Authenticate through Django's signed session middleware instead.
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.auth import get_user_model
    from django.conf import settings
    from django.contrib.auth import BACKEND_SESSION_KEY
    session_key=request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_key:return None
    session=SessionStore(session_key=session_key)
    try:
        uid=session.get("_auth_user_id")
        backend=session.get("_auth_user_backend")
        if not uid or backend not in settings.AUTHENTICATION_BACKENDS:return None
        user=get_user_model().objects.get(pk=uid)
        if session.get("_auth_user_hash")!=user.get_session_auth_hash():return None
    except (get_user_model().DoesNotExist,ValueError,TypeError):return None
    member=user.forecast_memberships.select_related("tenant").filter(tenant_id=session.get("tenant_id")).first() or user.forecast_memberships.select_related("tenant").first()
    if member is None:return None
    return series(member.tenant)

@router.get("/dashboard")
async def dashboard(request:Request):
    data=await sync_to_async(_read,thread_sensitive=True)(request)
    if data is None:raise HTTPException(status_code=401,detail="Login erforderlich")
    return data
