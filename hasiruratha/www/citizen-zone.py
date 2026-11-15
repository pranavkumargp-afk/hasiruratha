import frappe

from hasiruratha import citizen_api as ca

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/citizen-login"
		raise frappe.Redirect
	zone = frappe.form_dict.get("zone")
	context.no_breadcrumbs = True
	context.zone_name = frappe.db.get_value("HR Zone", zone, "zone_name") or zone
	sites = ca.zone_sites(zone)
	for s in sites:
		s["trees"] = ca.site_trees(s["site_id"])
	context.sites = sites
