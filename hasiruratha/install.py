# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
import frappe

ZONES = [
	("Z-JPN-001", "JP Nagar"),
	("Z-KAN-001", "Kanakapura"),
	("Z-BAN-001", "Bannerghatta"),
	("Z-BTM-001", "BTM / Koramangala"),
	("Z-OUT-001", "Outer Areas"),
	("Z-BSV-001", "Basavangudi"),
	("Z-JAY-001", "Jayanagar"),
]


def after_install():
	"""Idempotent - safe to run on every migrate."""
	_role("HR Admin", desk_access=1)
	_role("HR Volunteer", desk_access=0)      # volunteers use /hasiruratha only, never /app
	for zid, name in ZONES:
		if not frappe.db.exists("HR Zone", zid):
			frappe.get_doc({"doctype": "HR Zone", "zone_id": zid, "zone_name": name,
			                "group_id": "GRP-001", "active": 1}).insert(ignore_permissions=True)
	frappe.db.commit()


def _role(name, desk_access):
	# Frappe auto-creates roles named in DocType permissions (with desk access ON) before we run,
	# so always enforce the value we want, not just on first creation.
	if frappe.db.exists("Role", name):
		frappe.db.set_value("Role", name, "desk_access", desk_access)
	else:
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk_access}).insert(ignore_permissions=True)


def make_demo_data():
	"""Local testing only:  bench --site hasiruratha.localhost execute hasiruratha.install.make_demo_data"""
	from hasiruratha import api
	frappe.set_user("Administrator")
	spots = [
		("Kanakapura Rd near Metro", "kanakapura road", 12.8806, 77.5731, "Identified"),
		("JP Nagar 6th Phase", "jp nagar", 12.8975, 77.5855, "Planned"),
		("Jayanagar 4th Block", "jayanagar", 12.9250, 77.5938, "Planned"),
		("Bannerghatta Rd stretch", "bannerghatta road", 12.8900, 77.5977, "Completed"),
		("Sarjapur Rd", "sarjapur road", 12.9100, 77.6860, "Monitoring"),
	]
	for name, road, lat, lng, status in spots:
		s = api.add_site({"name": name, "road": road, "gps_lat": lat, "gps_lng": lng, "status": status,
		                  "site_type": "stretch" if "stretch" in name else "spot", "added_by": "Demo"})
		api.add_trees_bulk({"site_id": s["site_id"], "road": road, "trees": [
			{"species": "Neem", "tree_guard": "Yes", "support_pole": "No"},
			{"species": "Pongamia", "tree_guard": "No", "support_pole": "No"}]})
	first = frappe.get_all("HR Tree", pluck="name", limit=1)[0]
	api.add_condition({"tree_id": first, "reported_by": "Demo", "watering_needed": True})
	frappe.db.commit()
	print("demo data created")
