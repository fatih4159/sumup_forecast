from django.test import TestCase,Client
from django.contrib.auth.models import User
from .models import Tenant,Membership,Settings,SaleRow,defaults
from .dedup import row_fingerprint,unique_rows

class DuplicateTests(TestCase):
    def test_fingerprint_is_order_independent(self):
        self.assertEqual(row_fingerprint({"Datum":"1","Typ":"Verkauf"}),row_fingerprint({"Typ":"Verkauf","Datum":"1"}))
    def test_distinct_occurrences_are_preserved(self):
        rows=[{"Datum":"1"},{"Datum":"1"}]
        self.assertEqual(len(list(unique_rows(rows,set()))),2)
        keys=[k for k,_ in unique_rows(rows,set())]
        self.assertEqual(list(unique_rows(rows,set(keys))),[])

class TenantIsolationTests(TestCase):
    def setUp(self):
        self.u=User.objects.create_user(username="alice",password="strong-password-123")
        self.v=User.objects.create_user(username="bob",password="strong-password-456")
        self.a=Tenant.objects.create(name="A",slug="a",created_by=self.u)
        self.b=Tenant.objects.create(name="B",slug="b",created_by=self.v)
        Membership.objects.create(tenant=self.a,user=self.u,role="owner")
        Membership.objects.create(tenant=self.b,user=self.v,role="owner")
    def test_tenant_switch_is_guarded(self):
        c=Client();c.force_login(self.u)
        self.assertEqual(c.get("/tenant/b/").status_code,404)
    def test_duplicate_key_unique_per_tenant(self):
        SaleRow.objects.create(tenant=self.a,fingerprint="same:1",payload={"Datum":"1"})
        SaleRow.objects.create(tenant=self.b,fingerprint="same:1",payload={"Datum":"1"})
        self.assertEqual(SaleRow.objects.count(),2)
    def test_viewer_cannot_import(self):
        Membership.objects.filter(tenant=self.a,user=self.u).update(role="viewer")
        c=Client();c.force_login(self.u)
        self.assertEqual(c.post("/import/").status_code,403)
