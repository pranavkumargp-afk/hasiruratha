import json

import frappe

from hasiruratha import citizen_api as ca

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/citizen-login"
		raise frappe.Redirect
	context.no_breadcrumbs = True
	context.title = "Hasiru Ratha"
	ov = ca.overview()
	context.ov = ov
	context.charts = json.dumps({"months": ov["trees_per_month"], "status": ov["trees_by_status"]})
	context.full_name = frappe.utils.get_fullname(frappe.session.user)
	st = frappe.get_cached_doc("Hasiruratha Settings")
	context.about_title = st.about_title or "What Hasiru Ratha has built"
	context.about_text = st.about_text or ""
	context.facebook_url = st.facebook_url
	context.x_url = st.x_url
	context.milestones = sorted(st.get("milestones") or [], key=lambda m: str(m.year))
	context.gallery = [g for g in (st.get("gallery") or []) if g.image]
