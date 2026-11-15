# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
"""
Citizen portal API (/citizen).

* Login is phone number + email only (no OTP). An account is created on first use, with the
  "HR Citizen" role only. Admin accounts can never be opened this way.
* Citizens only ever see aggregate numbers, names of volunteers (never phone/email) and their OWN
  submissions. Every function below checks the session on the server.
* Photo is mandatory for planting and reporting. Location comes from the photo, the phone GPS,
  or a pin on the map; road/area are filled by reverse geocoding and can be edited.
"""
import secrets
from collections import Counter
from datetime import date

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_months, cint, flt, get_fullname, getdate, today, validate_email_address

from hasiruratha import api
from hasiruratha.hasiruratha.doctype.hr_site import hr_site as hs

CITIZEN_ROLE = "HR Citizen"
ISSUES = {"Dead tree": "High", "Damage": "High", "Pest / Disease": "Medium", "Watering": "Medium",
          "Leaning": "High", "Debris": "Low", "Guard / Support": "Medium", "Other": "Medium"}


# ───────────────────────────── helpers ─────────────────────────────
def _login_required():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in"), frappe.AuthenticationError)
	return frappe.session.user


def _check_photo(url):
	url = (url or "").strip()
	if not url.startswith(("/files/", "/private/files/")):
		frappe.throw(_("A photo is required"))
	name = frappe.db.get_value("File", {"file_url": url, "owner": frappe.session.user}, "name")
	if not name:
		frappe.throw(_("Photo not found. Please upload it again."))
	if url.startswith("/private/"):          # tree photos are shown on the public dashboard
		f = frappe.get_doc("File", name)
		f.is_private = 0
		f.save(ignore_permissions=True)
		url = f.file_url
	return url


def _todo_admins(ref_dt, ref_name, text):
	admins = frappe.get_all("Has Role", {"role": "HR Admin", "parenttype": "User"}, pluck="parent")
	for u in set(admins) - {"Administrator", "Guest"}:
		if frappe.db.get_value("User", u, "enabled"):
			frappe.get_doc({"doctype": "ToDo", "allocated_to": u, "reference_type": ref_dt,
			                "reference_name": ref_name, "priority": "Medium",
			                "description": text}).insert(ignore_permissions=True)


def _nominatim(lat, lng):
	import requests
	try:
		r = requests.get("https://nominatim.openstreetmap.org/reverse",
		                 params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1},
		                 headers={"User-Agent": "HasiruRatha/1.0 (plantation tracker)"}, timeout=8)
		j = r.json()
	except Exception:
		return {"success": False}
	a = j.get("address") or {}
	road = a.get("road") or a.get("pedestrian") or a.get("residential") or ""
	area = a.get("suburb") or a.get("neighbourhood") or a.get("quarter") or a.get("city_district") or ""
	return {"success": True, "road": road or area, "area": area, "address": j.get("display_name") or ""}


def suggest_zone(lat, lng, road, area):
	"""Zone from the nearest registered site (2 km), else from road/area words, else 'Outer Areas'."""
	near = [n for n in hs.get_nearby(lat, lng, 2000) if n.zone_id]
	if near:
		n = near[0]
		zone, note = n.zone_id, "Nearest registered site %s is %s m away" % (n.site_name or n.name, n.distance_m)
	else:
		zone = api._zone_for_road("%s %s" % (road or "", area or ""))
		note = "Matched by road/area name" if zone != "Z-OUT-001" else "No registered site nearby - admin please confirm the zone"
	if not frappe.db.exists("HR Zone", zone):
		zone = None
	return {"zone_id": zone, "zone_name": frappe.db.get_value("HR Zone", zone, "zone_name") if zone else "", "zone_note": note}


def _tree_row(t):
	return {"tree_id": t.tree_id, "species": t.species, "status": t.status, "condition": t.condition,
	        "photo_url": t.photo_url, "date_planted": str(t.date_planted or "")}


# ───────────────────────────── login ─────────────────────────────
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def citizen_login(phone=None, email=None, full_name=None):
	digits = api._digits(phone)
	phone10 = digits[-10:]
	email = (email or "").strip().lower()
	if len(digits) < 10:
		return {"success": False, "error": "Please enter a valid 10-digit mobile number"}
	if not validate_email_address(email):
		return {"success": False, "error": "Please enter a valid email"}

	user = frappe.db.get_value("User", {"email": email}, "name")
	if user:
		roles = set(frappe.get_roles(user))
		if api.PRIVILEGED & roles:
			return {"success": False, "error": "Admins sign in with the admin login"}
		if CITIZEN_ROLE not in roles:
			return {"success": False, "error": "This email is not registered here. Use a different email."}
		if api._last10(frappe.db.get_value("User", user, "mobile_no")) != phone10:
			return {"success": False, "error": "This email is registered with a different mobile number"}
		if not cint(frappe.db.get_value("User", user, "enabled")):
			return {"success": False, "error": "Account disabled"}
	else:
		if frappe.get_all("User", {"mobile_no": ["like", "%" + phone10]}, limit=1):
			return {"success": False, "error": "This mobile number is registered with a different email"}
		name = (full_name or "").strip()
		if not name:
			return {"success": True, "need_name": True}
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": name[:60], "mobile_no": phone10, "enabled": 1,
			"user_type": "Website User", "send_welcome_email": 0, "new_password": secrets.token_urlsafe(24),
			"roles": [{"role": CITIZEN_ROLE}],
		}).insert(ignore_permissions=True)
		user = email
	frappe.local.login_manager.login_as(user)
	return {"success": True}


# ───────────────────────────── dashboard (read only) ─────────────────────────────
@frappe.whitelist()
def overview():
	_login_required()
	sites = frappe.get_all("HR Site", {"status": ["!=", "Merged"]}, ["name", "zone_id"], limit_page_length=0)
	site_zone = {s.name: s.zone_id for s in sites}
	zones = frappe.get_all("HR Zone", {"active": 1}, ["zone_id", "zone_name"], order_by="zone_name")
	trees = frappe.get_all("HR Tree", fields=["status", "date_planted", "site_id"], limit_page_length=0)
	vols = frappe.get_all("HR Volunteer", {"active": 1}, ["volunteer_name", "area"], order_by="volunteer_name",
	                      limit_page_length=0)          # names only - never phone / email

	by_zone_sites, by_zone_trees = Counter(site_zone.values()), Counter(site_zone.get(t.site_id) for t in trees)
	months, today_ = [], date.today()
	for i in range(11, -1, -1):
		d = getdate(add_months(today_, -i))
		months.append((d.year, d.month))
	per_month = Counter((getdate(t.date_planted).year, getdate(t.date_planted).month) for t in trees if t.date_planted)
	return {
		"counts": {"trees": len(trees), "sites": len(sites), "zones": len(zones), "volunteers": len(vols)},
		"trees_per_month": [{"label": "%s %s" % (date(y, m, 1).strftime("%b"), str(y)[2:]), "value": per_month.get((y, m), 0)} for y, m in months],
		"trees_by_status": dict(Counter(t.status or "Identified" for t in trees)),
		"zones": [{"zone_id": z.zone_id, "zone_name": z.zone_name, "sites": by_zone_sites.get(z.zone_id, 0),
		           "trees": by_zone_trees.get(z.zone_id, 0)} for z in zones],
		"volunteers": [{"name": v.volunteer_name, "area": v.area or ""} for v in vols if v.volunteer_name],
	}


@frappe.whitelist()
def zone_sites(zone_id=None):
	_login_required()
	return frappe.get_all("HR Site", {"zone_id": zone_id, "status": ["!=", "Merged"]},
	                      ["site_id", "site_name", "road", "area", "tree_count", "status", "photo_url"],
	                      order_by="creation desc", limit_page_length=200)


@frappe.whitelist()
def site_trees(site_id=None):
	_login_required()
	return [_tree_row(t) for t in frappe.get_all(
		"HR Tree", {"site_id": site_id}, ["tree_id", "species", "status", "condition", "photo_url", "date_planted"],
		order_by="position", limit_page_length=200)]


# ───────────────────────────── location helpers ─────────────────────────────
@frappe.whitelist()
def locate(lat=None, lng=None, for_report=0):
	"""Road/area names + suggested zone + (planting) nearby spots / (report) nearby trees."""
	_login_required()
	lat, lng = flt(lat), flt(lng)
	if not (-90 <= lat <= 90 and -180 <= lng <= 180) or not (lat and lng):
		frappe.throw(_("Bad location"))
	key = "hr_cz_%.4f_%.4f" % (lat, lng)
	out = api._cache().get_value(key)
	if not out:
		g = api.reverse_geocode({"lat": lat, "lng": lng})
		if not g.get("success"):
			g = _nominatim(lat, lng)
		out = {"road": g.get("road") or "", "area": g.get("area") or "", "address": g.get("address") or ""}
		out.update(suggest_zone(lat, lng, out["road"], out["area"]))
		api._cache().set_value(key, out, expires_in_sec=3600)
	res = dict(out)
	if cint(for_report):
		trees = []
		for s in hs.get_nearby(lat, lng, 100):
			for t in frappe.get_all("HR Tree", {"site_id": s.name}, ["tree_id", "species", "status", "photo_url"], limit_page_length=20):
				trees.append({**_tree_row(frappe._dict(t, condition="", date_planted="")), "distance_m": s.distance_m,
				              "site_name": s.site_name or s.name, "road": s.road or s.area or ""})
		res["trees"] = sorted(trees, key=lambda x: x["distance_m"])[:8]
	else:
		res["spots"] = [{"site_id": s.name, "name": s.site_name or s.name, "road": s.road or s.area or "",
		                 "tree_count": s.tree_count or 0, "distance_m": s.distance_m}
		                for s in hs.get_nearby(lat, lng, 30, "spot")]
	return res


# ───────────────────────────── plant / report ─────────────────────────────
def _new_site_and_tree(user, lat, lng, species, road, area, address, photo, zone, status, notes, condition="Unknown"):
	full = get_fullname(user)
	label = (area or road or "Citizen spot")
	s = api.add_site({"name": "%s - %s" % (label, today()), "road": road, "area": area, "gps_lat": lat, "gps_lng": lng,
	                  "site_type": "spot", "zone_id": zone.get("zone_id"), "photo_url": photo, "status": status,
	                  "notes": notes, "added_by": full})
	frappe.db.set_value("HR Site", s["site_id"], {"submitted_via": "Citizen", "address_full": address,
	                                              "zone_note": zone.get("zone_note"), "admin_reviewed": 0})
	t = api.add_tree({"site_id": s["site_id"], "road": road, "area": area, "gps_lat": lat, "gps_lng": lng,
	                  "species": species, "photo_url": photo, "planted_by": full, "status": status,
	                  "condition": condition, "notes": notes, "position": 1})
	frappe.db.set_value("HR Tree", t["tree_id"], {"submitted_via": "Citizen", "admin_reviewed": 0})
	return s["site_id"], t["tree_id"]


def plant_core(user, photo, lat, lng, species, road, area, address, existing_site=None, confirm_new=0):
	"""Add a citizen's tree. Reuses an existing spot, or creates a new site + tree."""
	species = (species or "").strip()[:60] or "Not sure"
	road, area, address = (road or "").strip()[:140], (area or "").strip()[:140], (address or "").strip()[:400]
	zone = suggest_zone(lat, lng, road, area)
	if existing_site:
		s = frappe.db.get_value("HR Site", existing_site, ["name", "tree_count"], as_dict=True)
		if not s:
			frappe.throw(_("That spot was not found"))
		site_id = s.name
		t = api.add_tree({"site_id": site_id, "road": road, "area": area, "gps_lat": lat, "gps_lng": lng,
		                  "species": species, "photo_url": photo, "planted_by": get_fullname(user),
		                  "status": "Completed", "position": cint(s.tree_count) + 1})
		tree_id = t["tree_id"]
		frappe.db.set_value("HR Tree", tree_id, {"submitted_via": "Citizen", "admin_reviewed": 0})
		frappe.db.set_value("HR Site", site_id, "tree_count", frappe.db.count("HR Tree", {"site_id": site_id}))
	else:
		if not cint(confirm_new):
			near = hs.get_nearby(lat, lng, 30, "spot")
			if near:
				return {"success": False, "duplicate": True,
				        "spots": [{"site_id": n.name, "name": n.site_name or n.name, "distance_m": n.distance_m,
				                   "tree_count": n.tree_count or 0} for n in near]}
		site_id, tree_id = _new_site_and_tree(user, lat, lng, species, road, area, address, photo, zone, "Completed", "Planted by a citizen")
	_todo_admins("HR Tree", tree_id, _("Citizen planted a {0} at {1} ({2}). Zone suggestion: {3}. Please confirm.").format(
		species, area or road or site_id, site_id, zone.get("zone_name") or "none"))
	return {"success": True, "site_id": site_id, "tree_id": tree_id, "zone_id": zone.get("zone_id"),
	        "zone_name": zone.get("zone_name"), "zone_note": zone.get("zone_note")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=40, seconds=3600)
def submit_planting(photo_url=None, gps_lat=None, gps_lng=None, species=None, road=None, area=None,
                    address_full=None, existing_site=None, confirm_new=0):
	user = _login_required()
	photo = _check_photo(photo_url)
	lat, lng = flt(gps_lat), flt(gps_lng)
	if not (lat and lng):
		frappe.throw(_("We need the location. Allow GPS or pin it on the map."))
	return plant_core(user, photo, lat, lng, species, road, area, address_full, existing_site, confirm_new)


def nearest_tree(lat, lng, radius=100):
	"""Closest registered tree within `radius` metres, or None."""
	best = None
	for s in hs.get_nearby(lat, lng, radius):
		t = frappe.db.get_value("HR Tree", {"site_id": s.name}, "name")
		if t:
			return {"tree_id": t, "distance_m": s.distance_m, "site_id": s.name}
	return best


def report_core(user, photo, lat, lng, issue_type, description, tree_id, road, area, address):
	issue = issue_type if issue_type in ISSUES else "Other"
	road, area, address = (road or "").strip()[:140], (area or "").strip()[:140], (address or "").strip()[:400]
	zone = suggest_zone(lat, lng, road, area)
	untracked = False
	if not tree_id:
		# not in our records: save it as a flagged, unconfirmed entry so an admin can verify it
		untracked = True
		_, tree_id = _new_site_and_tree(user, lat, lng, "Unknown", road, area, address, photo, zone, "Identified",
		                                "Tree not in records. Reported by a citizen: %s" % issue, condition="Unknown")
	res = api.create_tree_report({"tree_id": tree_id, "issue_type": issue, "description": (description or "")[:500],
	                              "priority": ISSUES[issue], "photo_url": photo, "gps_lat": lat, "gps_lng": lng})
	if not res.get("success"):
		frappe.throw(res.get("error") or _("Could not save the report"))
	frappe.db.set_value("HR Tree Report", res["name"], {"submitted_via": "Citizen", "address_full": address,
	                                                    "zone_note": zone.get("zone_note"), "admin_reviewed": 0})
	_todo_admins("HR Tree Report", res["name"], _("Citizen report: {0} at {1}{2}. Zone suggestion: {3}.").format(
		issue, area or road or tree_id, " (tree not in records)" if untracked else "", zone.get("zone_name") or "none"))
	return {"success": True, "report_id": res["report_id"], "report_name": res["name"], "tree_id": tree_id,
	        "untracked": untracked, "zone_id": zone.get("zone_id"), "zone_note": zone.get("zone_note")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=40, seconds=3600)
def submit_report(photo_url=None, gps_lat=None, gps_lng=None, issue_type=None, description=None, tree_id=None,
                  road=None, area=None, address_full=None):
	user = _login_required()
	photo = _check_photo(photo_url)
	lat, lng = flt(gps_lat), flt(gps_lng)
	if not (lat and lng):
		frappe.throw(_("We need the location. Allow GPS or pin it on the map."))
	r = report_core(user, photo, lat, lng, issue_type, description, tree_id, road, area, address_full)
	return {"success": True, "report_id": r["report_id"], "untracked": r["untracked"]}


# ───────────────────────────── my status ─────────────────────────────
@frappe.whitelist()
def my_status():
	user = _login_required()
	trees = frappe.get_all("HR Tree", {"owner": user},
	                       ["tree_id", "species", "status", "condition", "photo_url", "date_planted", "site_id"],
	                       order_by="creation desc", limit_page_length=50)
	for t in trees:
		a = frappe.db.get_value("HR Site", t.site_id, ["area", "road"], as_dict=True) or {}
		t["place"] = a.get("area") or a.get("road") or ""
		t["date_planted"] = str(t.date_planted or "")
	reports = frappe.get_all("HR Tree Report", {"owner": user},
	                         ["report_id", "tree_id", "issue_type", "status", "reported_on", "assigned_volunteer_name",
	                          "resolved_on", "photo_url"], order_by="creation desc", limit_page_length=50)
	for r in reports:
		r["reported_on"], r["resolved_on"] = str(r.reported_on or ""), str(r.resolved_on or "")
	vol = frappe.db.get_value("HR Volunteer", {"user": user}, ["name", "active"], as_dict=True)
	app = None
	if vol:
		app = frappe.db.get_value("HR Application", {"volunteer": vol.name}, ["status", "application_date", "tree"],
		                          as_dict=True, order_by="creation desc")
		if app:
			app["application_date"] = str(app.application_date or "")
	return {"name": get_fullname(user), "trees": trees, "reports": reports,
	        "volunteer": {"active": cint(vol.active) if vol else 0, "application": app} if vol else None}


# ───────────────────────────── volunteer (email code, then admin approval) ─────────────────────────────
@frappe.whitelist(methods=["POST"])
@rate_limit(limit=6, seconds=3600)
def send_email_code(email=None):
	user = _login_required()
	email = (email or "").strip().lower()
	if not validate_email_address(email):
		frappe.throw(_("Please enter a valid email"))
	code = "%06d" % secrets.randbelow(10**6)
	api._cache().set_value("hr_vcode_%s" % user, {"code": code, "email": email, "tries": 0}, expires_in_sec=600)
	try:
		frappe.sendmail(recipients=[email], subject=_("Your Hasiru Ratha verification code"), now=True,
		                message=_("<p>Your verification code is <b>{0}</b>. It is valid for 10 minutes.</p>").format(code))
	except Exception:
		frappe.log_error(title="Hasiru Ratha: verification email failed")
		frappe.throw(_("We could not send the email right now. Please try again later."))
	return {"success": True}


def check_email_code(user, email, code):
	"""Raises unless `code` is the one we emailed to `email` for this user."""
	key = "hr_vcode_%s" % user
	data = api._cache().get_value(key)
	email = (email or "").strip().lower()
	if not data or data.get("email") != email:
		frappe.throw(_("Please request a new code"))
	if data["tries"] >= 5:
		api._cache().delete_value(key)
		frappe.throw(_("Too many wrong codes. Please request a new one."))
	if not secrets.compare_digest(str(code or "").strip(), data["code"]):
		data["tries"] += 1
		api._cache().set_value(key, data, expires_in_sec=600)
		frappe.throw(_("That code is not correct"))
	api._cache().delete_value(key)


def apply_core(user, email, area, reason, tree_id=None):
	"""Create the (inactive) volunteer and a Pending HR Application. Admin approves later."""
	phone = frappe.db.get_value("User", user, "mobile_no") or ""
	vol = frappe.db.get_value("HR Volunteer", {"user": user}, ["name", "active"], as_dict=True)
	if not vol:
		existing = api._find_volunteer(phone)
		if existing and cint(existing.active):
			return {"success": True, "already": True}
		vid = api._gen_id("VOL")
		frappe.get_doc({"doctype": "HR Volunteer", "volunteer_id": vid, "volunteer_name": get_fullname(user),
		                "phone": phone, "email": email, "area": (area or "")[:140], "group_id": api.GROUP,
		                "joined_date": getdate(today()), "active": 0, "user": user}).insert(ignore_permissions=True)
		vol = frappe._dict(name=vid, active=0)
	if cint(vol.active):
		return {"success": True, "already": True}
	pending = frappe.db.get_value("HR Application", {"volunteer": vol.name, "status": "Pending"}, "name")
	if pending:
		return {"success": True, "pending": True, "application": pending, "volunteer": vol.name}
	tree = tree_id if tree_id and frappe.db.exists("HR Tree", tree_id) else None
	app = frappe.get_doc({"doctype": "HR Application", "application_type": "Volunteer Application",
	                      "volunteer": vol.name, "tree": tree, "application_date": getdate(today()),
	                      "reason": (reason or "")[:500], "status": "Pending", "email_verified": 1}).insert(ignore_permissions=True)
	_todo_admins("HR Application", app.name, _("Volunteer application from {0} (email verified). Please review.").format(get_fullname(user)))
	return {"success": True, "application": app.name, "volunteer": vol.name}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def volunteer_apply(code=None, email=None, area=None, reason=None, tree_id=None):
	user = _login_required()
	check_email_code(user, email, code)
	return apply_core(user, (email or "").strip().lower(), area, reason, tree_id)


@frappe.whitelist(methods=["POST"])
def review_application(name=None, approve=1, notes=None):
	hs._require_admin()
	app = frappe.get_doc("HR Application", name)
	app.reviewed_by, app.review_date, app.review_notes = frappe.session.user, getdate(today()), (notes or "")[:500]
	if cint(approve):
		vol = frappe.get_doc("HR Volunteer", app.volunteer)
		vol.active = 1
		vol.save(ignore_permissions=True)
		if vol.user and frappe.db.exists("User", vol.user):
			frappe.get_doc("User", vol.user).add_roles(api.VOLUNTEER_ROLE)
		app.status = "Approved"
		if app.tree and not frappe.db.get_value("HR Tree", app.tree, "owner_volunteer_id"):
			frappe.db.set_value("HR Tree", app.tree, "owner_volunteer_id", vol.name)
			app.status = "Assigned"
	else:
		app.status = "Rejected"
	app.save(ignore_permissions=True)
	frappe.db.set_value("ToDo", {"reference_type": "HR Application", "reference_name": app.name, "status": "Open"}, "status", "Closed")
	return {"success": True, "status": app.status}


# ───────────────────────────── admin view of citizen submissions ─────────────────────────────
@frappe.whitelist()
def admin_submissions():
	hs._require_admin()
	out = []
	for t in frappe.get_all("HR Tree", {"submitted_via": "Citizen", "admin_reviewed": 0},
	                        ["name", "tree_id", "species", "status", "site_id", "photo_url", "owner", "creation", "notes"],
	                        order_by="creation desc", limit_page_length=50):
		out.append(_admin_row("Plant", t, t.site_id, None))
	for r in frappe.get_all("HR Tree Report", {"submitted_via": "Citizen", "admin_reviewed": 0},
	                        ["name", "report_id", "issue_type", "priority", "status", "site_id", "photo_url", "owner",
	                         "creation", "address_full", "zone_id", "zone_note", "gps_lat", "gps_lng", "tree_id"],
	                        order_by="creation desc", limit_page_length=50):
		out.append(_admin_row("Report", r, r.site_id, r))
	return sorted(out, key=lambda x: x["when"], reverse=True)


def _admin_row(kind, d, site_id, rep):
	s = frappe.db.get_value("HR Site", site_id, ["site_id", "road", "area", "zone_id", "zone_note", "address_full",
	                                             "gps_lat", "gps_lng"], as_dict=True) or {}
	return {
		"kind": kind, "name": d.name, "title": ("Planted: %s" % d.species) if kind == "Plant" else ("Report: %s" % d.issue_type),
		"detail": (d.notes if kind == "Plant" else ("Priority %s" % d.priority)), "tree_id": d.tree_id, "site_id": site_id,
		"photo_url": d.photo_url, "area": s.get("area"), "road": s.get("road"),
		"address": (rep.address_full if rep and rep.address_full else s.get("address_full")),
		"zone_id": (rep.zone_id if rep and rep.zone_id else s.get("zone_id")), "zone_note": (rep.zone_note if rep and rep.zone_note else s.get("zone_note")),
		"lat": (rep.gps_lat if rep and rep.gps_lat else s.get("gps_lat")), "lng": (rep.gps_lng if rep and rep.gps_lng else s.get("gps_lng")),
		"by": get_fullname(d.owner), "phone": frappe.db.get_value("User", d.owner, "mobile_no") or "", "when": str(d.creation),
	}


@frappe.whitelist(methods=["POST"])
def admin_review(kind=None, name=None, zone_id=None):
	"""Admin confirms (and optionally corrects the zone of) a citizen submission."""
	hs._require_admin()
	dt = "HR Tree" if kind == "Plant" else "HR Tree Report"
	site_id = frappe.db.get_value(dt, name, "site_id") if dt == "HR Tree Report" else frappe.db.get_value("HR Tree", name, "site_id")
	if zone_id and frappe.db.exists("HR Zone", zone_id):
		if site_id:
			frappe.db.set_value("HR Site", site_id, "zone_id", zone_id)
		if dt == "HR Tree Report":
			frappe.db.set_value(dt, name, "zone_id", zone_id)
	frappe.db.set_value(dt, name, "admin_reviewed", 1)
	if site_id:
		frappe.db.set_value("HR Site", site_id, "admin_reviewed", 1)
	for t in frappe.get_all("ToDo", {"reference_type": dt, "reference_name": name, "status": "Open"}, pluck="name"):
		frappe.db.set_value("ToDo", t, "status", "Closed")
	return {"success": True}
