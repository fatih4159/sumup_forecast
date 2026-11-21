from fastapi import APIRouter,HTTPException,Request
from asgiref.sync import sync_to_async
router=APIRouter()

@router.get("/health")
def health():
    return {"status":"ok"}

def _read(request):
    from .services import series
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.auth import get_user_model
    from django.conf import settings
    from django.utils.crypto import constant_time_compare
    session_key=request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_key:return None
    session=SessionStore(session_key=session_key)
    try:
        uid=session.get("_auth_user_id")
        backend=session.get("_auth_user_backend")
        if not uid or backend not in settings.AUTHENTICATION_BACKENDS:return None
        user=get_user_model().objects.get(pk=uid,is_active=True)
        stored=session.get("_auth_user_hash")
        if not stored or not constant_time_compare(stored,user.get_session_auth_hash()):return None
    except (get_user_model().DoesNotExist,ValueError,TypeError):return None
    membership=user.forecast_memberships.select_related("tenant").filter(tenant_id=session.get("tenant_id")).first()
    if membership is None:
        membership=user.forecast_memberships.select_related("tenant").first()
    if membership is None:return None
    return series(membership.tenant)

@router.get("/dashboard")
async def dashboard(request:Request):
    data=await sync_to_async(_read,thread_sensitive=True)(request)
    if data is None:raise HTTPException(status_code=401,detail="Login erforderlich")
    return data
