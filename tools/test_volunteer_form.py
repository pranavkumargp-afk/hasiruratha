import sys, json
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frappe
from unittest import mock
frappe.init(site="test", sites_path="/tmp/sites")
frappe.local.lang = "en"
import frappe.translate as _t
_t.get_all_translations = lambda lang: {}

from hasiruratha import citizen_forms as cf, citizen_api as ca

ok = lambda m: print("PASS", m)
def throws(fn, *needles):
    try: fn()
    except frappe.ValidationError as e:
        msg = str(e)
        assert all(n in msg for n in needles), msg
        return msg
    raise AssertionError("expected a ValidationError")

def doc(**kw):
    base = dict(owner="a@x.com", full_name="Asha K", mobile="9876543210", email="a@x.com", address="12, 3rd cross",
                road="Ashoka Pillar Rd", area="Jayanagar 2nd Block", zone="Z-JAY-001", pincode="560011",
                verification_code="123456", tree_preference="", reason="")
    base.update(kw); d = frappe._dict(base); return d

# 1. missing fields are all listed in one message
msg = throws(lambda: cf.before_volunteer(doc(road="", pincode="")), "Road", "Pin code"); ok("missing fields reported together: " + msg)
# 2. bad pin code
throws(lambda: cf.before_volunteer(doc(pincode="5600")), "6 digits"); ok("pin code must be 6 digits")
# 3. good data goes on to the e-mail code check (stubbed) and clears the code
with mock.patch.object(ca, "check_email_code") as chk:
    d = doc(); cf.before_volunteer(d)
    chk.assert_called_once_with("a@x.com", "a@x.com", "123456")
    assert d.email_verified == 1 and d.verification_code == ""
ok("valid form passes to code check, email_verified set, code wiped")

# 4. apply_core: a NEW volunteer gets the form's profile; HR Application is created with NO tree (the old crash)
created = []
class FakeDoc:
    def __init__(self, d): self.d = d; self.name = d.get("volunteer_id") or "APP-1"
    def insert(self, **k): created.append(self.d); return self
def fake_get_value(dt, filt=None, fields=None, **k):
    if dt == "User": return "9000000000" if fields == "mobile_no" else None
    return None
frappe.local.db = mock.MagicMock(); frappe.local.db.get_value.side_effect = fake_get_value
with mock.patch.object(frappe, "get_doc", side_effect=lambda d: FakeDoc(d)), \
     mock.patch.object(ca.api, "_find_volunteer", return_value=None), \
     mock.patch.object(ca.api, "_gen_id", return_value="VOL-9"), \
     mock.patch.object(ca, "_todo_admins"), mock.patch.object(ca, "today", return_value="2026-11-20"), mock.patch.object(ca, "get_fullname", return_value="Fallback Name"):
    r = ca.apply_core("a@x.com", "a@x.com", "Jayanagar 2nd Block", "I love trees",
                      profile=dict(full_name="Asha K", mobile="9876543210", address="12, 3rd cross", road="Ashoka Pillar Rd",
                                   pincode="560011", zone="Z-JAY-001"))
vol, app = created
assert vol["doctype"] == "HR Volunteer" and vol["volunteer_name"] == "Asha K" and vol["phone"] == "9876543210"
assert vol["primary_zone_id"] == "Z-JAY-001" and vol["pincode"] == "560011" and vol["road"] == "Ashoka Pillar Rd" and vol["active"] == 0
assert app["doctype"] == "HR Application" and app["tree"] is None and app["status"] == "Pending" and app["email_verified"] == 1
assert r["success"] and r["volunteer"] == "VOL-9"
ok("apply_core: volunteer saved with name/mobile/zone/pincode, inactive; application created with tree=None")

# 5. DocType metadata the insert depends on
import glob
hv = json.load(open("hasiruratha/hasiruratha/doctype/hr_volunteer/hr_volunteer.json"))
ha = json.load(open("hasiruratha/hasiruratha/doctype/hr_application/hr_application.json"))
assert {"address", "road", "pincode", "primary_zone_id"} <= {f["fieldname"] for f in hv["fields"]}
assert [f for f in ha["fields"] if f["fieldname"] == "tree"][0]["reqd"] == 0
ok("HR Volunteer has the new fields; HR Application.tree is no longer mandatory")

# 6. HR Application controller: Admin Assignment still needs a tree
from hasiruratha.hasiruratha.doctype.hr_application.hr_application import HRApplication
a = HRApplication.__new__(HRApplication); a.application_type = "Admin Assignment"; a.tree = None
throws(lambda: HRApplication.validate(a), "Tree is mandatory"); ok("Admin Assignment without a tree is still rejected")
a.application_type = "Volunteer Application"; HRApplication.validate(a); ok("Volunteer Application without a tree is accepted")

# 7. whitelisted API surface used by the form
for fn in ("my_profile", "send_email_code", "volunteer_apply"):
    assert getattr(ca, fn) in frappe.whitelisted, fn
ok("my_profile / send_email_code / volunteer_apply are whitelisted")
print("\nALL TESTS PASSED")
