from django.http import Http404
from .models import Membership,Tenant
def active_tenant(request):
    memberships=Membership.objects.filter(user=request.user).select_related("tenant").order_by("tenant__name")
    selected=request.session.get("tenant_id")
    membership=memberships.filter(tenant_id=selected).first() if selected else None
    membership=membership or memberships.first()
    if not membership: raise Http404("Kein Mandant zugeordnet")
    return membership.tenant,membership,list(memberships)
