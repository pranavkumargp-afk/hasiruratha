# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
"""
HR Site - with duplicate detection.

A NEW site is flagged "Needs Review" (never blocked) when, among sites of the same type that
are not Merged, there is one that is
  * within DUPLICATE_RADIUS_M metres, OR
  * on the same road + area and within SAME_ROAD_RADIUS_M metres.
(Road+area alone would flag every site on a long road, so it is paired with a distance cap.)
The admin then approves it as a new site or merges it into the existing one.
"""
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

DUPLICATE_RADIUS_M = 25
SAME_ROAD_RADIUS_M = 150
NEAR_ME_RADIUS_M = 300
ADMIN_ROLES = {"HR Admin", "System Manager", "Administrator"}


def haversine(lat1, lng1, lat2, lng2):
	r = 6371000.0
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dphi, dl = p2 - p1, math.radians(lng2 - lng1)
	a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * r * math.asin(math.sqrt(a))


def _norm(s):
	return " ".join(str(s or "").lower().split())


def get_nearby(lat, lng, radius=NEAR_ME_RADIUS_M, site_type=None, exclude=None):
	"""Sites within `radius` metres, closest first. Merged sites are never returned."""
	lat, lng, radius = flt(lat), flt(lng), flt(radius)
	if not (lat and lng):
		return []
	dlat = radius / 111320.0
	dlng = radius / (111320.0 * max(math.cos(math.radians(lat)), 0.01))
	filters = {
		"gps_lat": ["between", [lat - dlat, lat + dlat]],
		"gps_lng": ["between", [lng - dlng, lng + dlng]],
		"status": ["!=", "Merged"],
	}
	if site_type:
		filters["site_type"] = site_type
	rows = frappe.get_all(
		"HR Site", filters=filters,
		fields=["name", "site_id", "site_name", "site_type", "status", "road", "area",
		        "zone_id", "tree_count", "gps_lat", "gps_lng", "photo_url"],
		limit_page_length=0,
	)
	out = []
	for r in rows:
		if exclude and r.name == exclude:
			continue
		d = haversine(lat, lng, flt(r.gps_lat), flt(r.gps_lng))
		if d <= radius:
			r["distance_m"] = round(d)
			out.append(r)
	return sorted(out, key=lambda x: x["distance_m"])


def find_duplicate(lat, lng, site_type, road, area, exclude=None):
	for c in get_nearby(lat, lng, SAME_ROAD_RADIUS_M, site_type or "spot", exclude):
		if c["distance_m"] <= DUPLICATE_RADIUS_M:
			return c
		if _norm(road) and _norm(road) == _norm(c.road) and _norm(area) == _norm(c.area):
			return c
	return None


class HRSite(Document):
	def validate(self):
		self.flag_possible_duplicate()

	def flag_possible_duplicate(self):
		if not self.is_new() or self.flags.ignore_duplicate_check or self.possible_duplicate_of:
			return
		if not (flt(self.gps_lat) and flt(self.gps_lng)):
			return
		match = find_duplicate(self.gps_lat, self.gps_lng, self.site_type, self.road, self.area,
		                       exclude=self.name)
		if match:
			self.status = "Needs Review"
			self.possible_duplicate_of = match["name"]

	def after_insert(self):
		if self.status == "Needs Review" and self.possible_duplicate_of:
			_notify_admins(self)


def _notify_admins(doc):
	admins = frappe.get_all("Has Role", {"role": "HR Admin", "parenttype": "User"}, pluck="parent")
	for u in set(admins) - {"Administrator", "Guest"}:
		if not frappe.db.get_value("User", u, "enabled"):
			continue
		frappe.get_doc({
			"doctype": "ToDo", "allocated_to": u, "reference_type": "HR Site",
			"reference_name": doc.name, "priority": "Medium",
			"description": _("Possible duplicate site: {0} is close to {1}. Please approve or merge.").format(
				doc.name, doc.possible_duplicate_of),
		}).insert(ignore_permissions=True)


def _require_admin():
	if not (ADMIN_ROLES & set(frappe.get_roles())):
		frappe.throw(_("Only an admin can do this"), frappe.PermissionError)


def _close_todos(name):
	for t in frappe.get_all("ToDo", {"reference_type": "HR Site", "reference_name": name, "status": "Open"}, pluck="name"):
		frappe.db.set_value("ToDo", t, "status", "Closed")


@frappe.whitelist()
def approve_site(name):
	"""Admin: this is genuinely a different site."""
	_require_admin()
	doc = frappe.get_doc("HR Site", name)
	doc.flags.ignore_duplicate_check = True
	doc.status, doc.possible_duplicate_of = "Identified", None
	doc.save(ignore_permissions=True)
	_close_todos(name)
	return {"success": True}


@frappe.whitelist()
def merge_site(name, into=None):
	"""Admin: same place as `into` (default: Possible Duplicate Of). Moves trees, visits, reports."""
	_require_admin()
	dup = frappe.get_doc("HR Site", name)
	target = into or dup.possible_duplicate_of
	if not target or target == name or not frappe.db.exists("HR Site", target):
		frappe.throw(_("Choose a different existing site to merge into"))
	for dt in ("HR Tree", "HR Visit", "HR Condition", "HR Tree Report"):
		frappe.db.sql("update `tab%s` set site_id=%%s where site_id=%%s" % dt, (target, name))
	count = frappe.db.count("HR Tree", {"site_id": target})
	frappe.db.set_value("HR Site", target, "tree_count", count)
	frappe.db.set_value("HR Site", name, {
		"status": "Merged", "possible_duplicate_of": target, "tree_count": 0,
		"notes": ((dup.notes or "") + "\nMerged into %s by %s" % (target, frappe.session.user)).strip(),
	})
	_close_todos(name)
	return {"success": True, "merged_into": target}
