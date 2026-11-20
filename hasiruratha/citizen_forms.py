# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
"""Glue between the three citizen Web Forms and the real data (HR Site / HR Tree / HR Tree Report /
HR Application). A citizen's submission is saved first (it is the admin's inbox), then processed."""
import json
import re

import frappe
from frappe import _
from frappe.utils import flt, get_fullname, getdate, today

from hasiruratha import citizen_api as ca


def _coords(doc):
	lat, lng = flt(doc.latitude), flt(doc.longitude)
	if doc.location:                      # a pin dropped on the map wins
		try:
			for f in json.loads(doc.location).get("features", []):
				if (f.get("geometry") or {}).get("type") == "Point":
					lng, lat = f["geometry"]["coordinates"][:2]
					break
		except Exception:
			pass
	return flt(lat), flt(lng)


def _prepare(doc):
	lat, lng = _coords(doc)
	if not (lat and lng):
		frappe.throw(_("We need the location. Allow GPS on your phone, or drop a pin on the map."))
	doc.latitude, doc.longitude = lat, lng
	doc.photo = ca._check_photo(doc.photo)
	if not (doc.area or doc.road):
		g = ca.locate(lat, lng)
		doc.area, doc.road, doc.address = g.get("area"), g.get("road"), g.get("address")


# ───────────── plant ─────────────
def before_plant(doc):
	_prepare(doc)


def after_plant(doc):
	site = None if doc.different_spot else (doc.existing_site or None)
	r = ca.plant_core(doc.owner, doc.photo, doc.latitude, doc.longitude, doc.tree_type, doc.road, doc.area,
	                  doc.address, existing_site=site, confirm_new=1 if doc.different_spot else 0)
	if r.get("duplicate"):                # a registered spot is within 30 m and the citizen did not say "different"
		r = ca.plant_core(doc.owner, doc.photo, doc.latitude, doc.longitude, doc.tree_type, doc.road, doc.area,
		                  doc.address, existing_site=r["spots"][0]["site_id"])
	doc.db_set({"site": r["site_id"], "tree": r["tree_id"], "zone": r.get("zone_id"), "zone_note": r.get("zone_note"),
	            "status": "On the map" if r.get("zone_id") else "Needs a check"}, update_modified=False)


# ───────────── report ─────────────
def before_report(doc):
	_prepare(doc)


def after_report(doc):
	near = ca.nearest_tree(doc.latitude, doc.longitude, 100)
	r = ca.report_core(doc.owner, doc.photo, doc.latitude, doc.longitude, doc.issue_type, doc.notes,
	                   near["tree_id"] if near else None, doc.road, doc.area, doc.address)
	doc.db_set({"tree": r["tree_id"], "report": r["report_name"], "untracked": 1 if r["untracked"] else 0,
	            "zone": r.get("zone_id"), "zone_note": r.get("zone_note")}, update_modified=False)


_REPORT_STATUS = {"Open": "Received", "Acknowledged": "Seen", "Assigned": "Volunteer assigned",
                  "In Progress": "In progress", "On Hold": "On hold", "Resolved": "Resolved"}


def sync_report_status(doc, method=None):
	"""HR Tree Report changed -> keep the citizen's copy up to date."""
	for name in frappe.get_all("HR Citizen Report", {"report": doc.name}, pluck="name"):
		frappe.db.set_value("HR Citizen Report", name, {
			"status": _REPORT_STATUS.get(doc.status, "Seen"),
			"assigned_volunteer": doc.get("assigned_volunteer_name") or "",
			"resolved_on": doc.get("resolved_on") or None})


# ───────────── volunteer ─────────────
_VOLUNTEER_REQUIRED = (("full_name", "Name"), ("mobile", "Mobile number"), ("email", "Email"), ("address", "Address"),
                       ("road", "Road"), ("area", "Area"), ("zone", "Zone"), ("pincode", "Pin code"))


def before_volunteer(doc):
	missing = [label for f, label in _VOLUNTEER_REQUIRED if not (doc.get(f) or "").strip()]
	if missing:
		frappe.throw(_("Please fill in: {0}").format(", ".join(missing)))
	if not re.fullmatch(r"\d{6}", doc.pincode.strip()):
		frappe.throw(_("Pin code must be 6 digits"))
	ca.check_email_code(doc.owner, doc.email, doc.verification_code)
	doc.email_verified = 1
	doc.verification_code = ""


def after_volunteer(doc):
	r = ca.apply_core(doc.owner, (doc.email or "").lower(), doc.area, doc.reason or doc.tree_preference,
	                  profile={"full_name": doc.full_name, "mobile": doc.mobile, "address": doc.address,
	                           "road": doc.road, "pincode": doc.pincode, "zone": doc.zone})
	doc.db_set({"volunteer": r.get("volunteer"), "application": r.get("application"),
	            "status": "Approved" if r.get("already") else "Pending"}, update_modified=False)


def sync_application_status(doc, method=None):
	for name in frappe.get_all("HR Volunteer Request", {"application": doc.name}, pluck="name"):
		st = "Approved" if doc.status in ("Approved", "Assigned", "Completed") else "Rejected" if doc.status == "Rejected" else "Pending"
		frappe.db.set_value("HR Volunteer Request", name, "status", st)


# ───────────── admin fixes the zone on a submission ─────────────
def zone_changed(doc, kind):
	if doc.is_new() or not doc.has_value_changed("zone") or not doc.zone:
		return
	if kind == "site" and doc.site:
		frappe.db.set_value("HR Site", doc.site, {"zone_id": doc.zone, "admin_reviewed": 1})
	elif kind == "report" and doc.report:
		site = frappe.db.get_value("HR Tree Report", doc.report, "site_id")
		frappe.db.set_value("HR Tree Report", doc.report, {"zone_id": doc.zone, "admin_reviewed": 1})
		if site:
			frappe.db.set_value("HR Site", site, "zone_id", doc.zone)
