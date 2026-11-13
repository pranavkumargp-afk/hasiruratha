import frappe
from frappe import _
from frappe.utils import flt

from hasiruratha import api
from hasiruratha.hasiruratha.doctype.hr_site import hr_site as hs


@frappe.whitelist()
def get_console_data():
	hs._require_admin()
	sites = frappe.get_all(
		"HR Site", filters={"status": ["!=", "Merged"]},
		fields=["name", "site_id", "site_name", "site_type", "status", "zone_id", "road", "area",
		        "gps_lat", "gps_lng", "tree_count", "possible_duplicate_of"],
		limit_page_length=0)
	by_id = {s.name: s for s in sites}
	queue = []
	for s in sites:
		if s.status == "Needs Review" and s.possible_duplicate_of:
			o = by_id.get(s.possible_duplicate_of) or frappe.db.get_value(
				"HR Site", s.possible_duplicate_of, ["name", "site_name", "gps_lat", "gps_lng"], as_dict=True)
			d = None
			if o and flt(o.gps_lat) and flt(s.gps_lat):
				d = round(hs.haversine(flt(s.gps_lat), flt(s.gps_lng), flt(o.gps_lat), flt(o.gps_lng)))
			queue.append({"site_id": s.name, "site_name": s.site_name, "other_id": s.possible_duplicate_of,
			              "other_name": o.site_name if o else "", "distance_m": d})
	return {
		"sites": sites,
		"queue": queue,
		"trees": frappe.get_all("HR Tree", fields=["tree_id", "site_id", "species", "owner_volunteer_id"],
		                        limit_page_length=0),
		"volunteers": frappe.get_all("HR Volunteer", filters={"active": 1},
		                             fields=["volunteer_id", "volunteer_name"], limit_page_length=0),
		"reports": frappe.get_all("HR Tree Report", filters={"status": ["in", ["Open", "Assigned"]]},
		                          fields=["report_id", "tree_id", "issue_type", "status"], limit_page_length=0),
		"counts": {
			"review": len(queue),
			"applications": frappe.db.count("HR Application", {"status": "Pending"}),
			"reports": frappe.db.count("HR Tree Report", {"status": "Open"}),
		},
	}


def _check(res):
	if not res.get("success"):
		frappe.throw(res.get("error") or _("Something went wrong"))
	return res


@frappe.whitelist(methods=["POST"])
def plan_visit(**b):
	hs._require_admin()
	b.pop("cmd", None)
	return _check(api.add_visit(b))


@frappe.whitelist(methods=["POST"])
def report_tree(**b):
	hs._require_admin()
	b.pop("cmd", None)
	return _check(api.create_tree_report(b))


@frappe.whitelist(methods=["POST"])
def assign(tree_id=None, report_id=None, volunteer_id=None):
	hs._require_admin()
	if report_id:
		return _check(api.assign_tree_report({"report_id": report_id, "volunteer_id": volunteer_id}))
	return _check(api.assign_tree({"tree_id": tree_id, "volunteer_id": volunteer_id}))
