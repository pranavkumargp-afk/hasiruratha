import frappe
from frappe.rate_limiter import rate_limit
from frappe import _
from hasiruratha.api import _is_admin, _is_member

DOCS = {
    "zones": "HR Zone",
    "sites": "HR Site",
    "trees": "HR Tree",
    "volunteers": "HR Volunteer",
}


def _normalize(key, row):
    row = dict(row)

    if key in ("sites", "trees"):
        row.setdefault("zone", row.get("zone_id"))
        row.setdefault("latitude", row.get("gps_lat"))
        row.setdefault("longitude", row.get("gps_lng"))

    if key == "trees":
        row.setdefault("site", row.get("site_id"))
        row.setdefault("owner", row.get("owner_volunteer_id") or row.get("owner_volunteer"))

    if key == "volunteers":
        row.setdefault("zone", row.get("primary_zone_id"))
        row.setdefault("status", "Active" if row.get("active") else "Inactive")
        row.setdefault("owner", row.get("volunteer_id"))

    return row


@frappe.whitelist()
def get_dashboard():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in"), frappe.AuthenticationError)

    if not _is_member():
        frappe.throw(_("You are not permitted to access Hasiru Ratha"), frappe.PermissionError)

    admin = _is_admin()

    out = {
        "user": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
        "me": frappe.session.user,
        "is_admin": admin,
        "errors": [],
        "fields": {},
    }

    for key, doctype in DOCS.items():
        if key == "volunteers" and not admin:
            out[key] = []
            continue

        try:
            rows = frappe.get_list(
                doctype,
                fields=["*"],
                limit_page_length=3000,
                order_by="creation desc",
            )
            out[key] = [_normalize(key, row) for row in rows]
            out["fields"][key] = [
                field.fieldname for field in frappe.get_meta(doctype).fields
            ]
        except Exception as exc:
            out[key] = []
            out["errors"].append(f"{doctype}: {str(exc)}")

    return out


@frappe.whitelist(methods=["POST"])
def set_status(name, status):
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in"), frappe.AuthenticationError)

    if not _is_member() or not _is_admin():
        frappe.throw(_("Only administrators can change site status"), frappe.PermissionError)

    doc = frappe.get_doc("HR Site", name)
    doc.check_permission("write")

    field = next(
        (field for field in ("status", "workflow_state") if doc.meta.has_field(field)),
        None,
    )

    if not field:
        frappe.throw(_("HR Site has no status field"))

    field_meta = doc.meta.get_field(field)
    allowed = [
        value.strip()
        for value in (field_meta.options or "").splitlines()
        if value.strip()
    ]

    if allowed and status not in allowed:
        frappe.throw(_("Invalid site status"))

    doc.set(field, status)
    doc.save()
    return {"success": True, "status": status}


@frappe.whitelist()
def check_admin_session():
    if frappe.session.user == "Guest":
        return {"success": False, "is_admin": False}

    return {
        "success": True,
        "is_admin": _is_admin(),
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=300)
def admin_login(phone=None, password=None):
    """Authenticate a Hasiru Ratha admin and create a Frappe session."""
    from frappe import _
    from frappe.twofactor import should_run_2fa

    phone = "".join(c for c in str(phone or "") if c.isdigit())
    password = str(password or "")

    if not phone or not password:
        frappe.throw(_("Enter mobile number and password."), frappe.AuthenticationError)

    if frappe.get_system_settings("disable_user_pass_login"):
        frappe.throw(_("Password login is disabled."), frappe.AuthenticationError)

    manager = frappe.local.login_manager
    manager.run_trigger("before_login")
    frappe.clear_cache(user=phone)
    users = frappe.get_all(
        "User",
        filters={"enabled": 1},
        fields=["name", "mobile_no"]
    )

    account = next(
        (
            u.name for u in users
            if "".join(c for c in str(u.mobile_no or "") if c.isdigit())[-10:] == phone[-10:]
        ),
        None
    )

    if not account:
        frappe.throw(_("No account found for this mobile number."), frappe.AuthenticationError)

    manager.authenticate(user=account, pwd=password)

    if not _is_admin(manager.user):
        frappe.throw(_("This account does not have admin access."), frappe.PermissionError)

    if should_run_2fa(manager.user):
        frappe.throw(_("Two-factor authentication needs a separate verification step."), frappe.AuthenticationError)

    if manager.force_user_to_reset_password():
        frappe.throw(_("A password reset is required."), frappe.AuthenticationError)

    frappe.form_dict.pop("password", None)
    manager.post_login()

    return {"success": True, "is_admin": True}
