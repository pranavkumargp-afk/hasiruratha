# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
"""
Hasiru Ratha backend.

This is a Python port of the Google Apps Script web app (Code.gs). The browser
app calls ONE endpoint, `hasiruratha.api.call`, with the same action names the
Apps Script used (getSites, addTree, ...). Everything else here is new:

    login_phone / register_phone  -> mobile-number sign-in -> real Frappe session
    upload_photo                  -> replaces the Cloudflare worker + Google Drive
    reverse_geocode (action)      -> replaces the browser -> Google Geocoding call
"""

import base64
import json
import re
import secrets
import time
from datetime import date, datetime

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, getdate, today

GROUP = "GRP-001"
VOLUNTEER_ROLE = "HR Volunteer"
ADMIN_ROLE = "HR Admin"
PRIVILEGED = {"HR Admin", "System Manager", "Administrator"}

# ── static maps (same as Code.gs, plus the two extra zones seen in the live app)
ZONE_ROAD_MAP = {
	"bannerghatta": "Z-BAN-001", "hulimavu": "Z-BAN-001", "arekere": "Z-BAN-001",
	"kanakapura": "Z-KAN-001", "uttarahalli": "Z-KAN-001", "gottigere": "Z-KAN-001",
	"kathriguppe": "Z-KAN-001",
	"jp nagar": "Z-JPN-001",
	"jayanagar": "Z-JAY-001",
	"basavanagudi": "Z-BSV-001", "basavangudi": "Z-BSV-001",
	"btm": "Z-BTM-001", "koramangala": "Z-BTM-001", "hosur": "Z-BTM-001",
	"sarjapur": "Z-OUT-001", "outer ring": "Z-OUT-001", "nice road": "Z-OUT-001",
	"electronic city": "Z-OUT-001", "bellandur": "Z-OUT-001", "varthur": "Z-OUT-001",
}
AREA_CODES = {
	"bannerghatta road": "BAN", "kanakapura road": "KAN", "hosur road": "HOS",
	"jp nagar": "JPN", "jayanagar": "JAY", "btm layout": "BTM", "koramangala": "KOR",
	"sarjapur road": "SAR", "outer ring road (south)": "ORR", "nice road corridor": "NCE",
	"uttarahalli road": "UTT", "kathriguppe road": "KAT", "electronic city": "ELC",
	"begur road": "BEG", "gottigere": "GOT", "hulimavu": "HUL", "bellandur": "BEL",
	"varthur road": "VAR", "shankarpuram": "SHA", "basavanagudi": "BSV",
	"basavangudi": "BSV", "default": "BLR",
}

# ── per-DocType serialisation rules --------------------------------------------------
# rename: DocType fieldname -> key the browser app expects (Sheet column name)
SPEC = {
	"HR Zone": dict(rename={}, geo=(), bools=("active",)),
	"HR Site": dict(rename={"site_name": "name"}, geo=("gps_lat", "gps_lng", "gps_lat2", "gps_lng2"), bools=()),
	"HR Tree": dict(rename={}, geo=("gps_lat", "gps_lng"), bools=()),
	"HR Visit": dict(rename={}, geo=(), bools=()),
	"HR Condition": dict(
		rename={}, geo=(),
		bools=("watering_needed", "guard_damaged", "guard_removal_needed", "guard_needed",
		       "support_pole_needed", "pesticide_needed", "debris", "leaning", "dead",
		       "healthy", "new_growth", "resolved"),
	),
	"HR Volunteer": dict(rename={"volunteer_name": "name"}, geo=(), bools=("active",)),
}


# ════════════════════════════════════════════════════════════════════════════════════
#  small helpers
# ════════════════════════════════════════════════════════════════════════════════════
def _cache():
	# frappe.cache() on v15, frappe.cache on v16
	return frappe.cache() if callable(frappe.cache) else frappe.cache


def _cols(dt):
	"""Fieldnames of data-carrying fields of a DocType (excludes layout fields)."""
	no_value = set(frappe.model.no_value_fields)
	return [df.fieldname for df in frappe.get_meta(dt).fields if df.fieldtype not in no_value]


def _ser(dt, row):
	spec = SPEC[dt]
	cols = set(_cols(dt))
	out = {}
	for k, v in row.items():
		if k not in spec["rename"] and k not in cols:
			continue
		if isinstance(v, (date, datetime)):
			v = str(v)[:10]
		if v == "":
			v = None
		if k in spec["geo"] and not v:
			v = None
		if k in spec["bools"]:
			v = bool(cint(v))
		out[spec["rename"].get(k, k)] = v
	return out


def _list(dt, filters=None, order_by="creation asc"):
	rows = frappe.get_all(
		dt, filters=filters or {}, fields=["name"] + _cols(dt),
		order_by=order_by, limit_page_length=0,
	)
	return [_ser(dt, r) for r in rows]


def _coerce(df, v):
	t = df.fieldtype
	if t == "Check":
		return 1 if v in (True, 1, "1", "true", "True", "TRUE") else 0
	if t == "Int":
		return cint(v) if v not in ("", None) else 0
	if t in ("Float", "Currency"):
		return flt(v) if v not in ("", None) else 0
	if t == "Date":
		return getdate(v) if v not in ("", None) else None
	if t == "Link":
		return v or None
	return v if isinstance(v, str) else ("" if v is None else str(v))


def _values(dt, body, skip=()):
	"""Browser payload -> DocType values. Unknown keys are ignored; None means 'leave alone'."""
	inv = {v: k for k, v in SPEC[dt]["rename"].items()}
	meta = frappe.get_meta(dt)
	cols = set(_cols(dt))
	vals = {}
	for k, v in (body or {}).items():
		k = inv.get(k, k)
		if k in skip or k not in cols or v is None:
			continue
		vals[k] = _coerce(meta.get_field(k), v)
	return vals


def _update(dt, name, updates):
	if not frappe.db.exists(dt, name):
		return {"success": False, "error": "Row not found: %s" % name}
	doc = frappe.get_doc(dt, name)
	doc.update(updates)
	doc.save(ignore_permissions=True)
	return {"success": True}


def _delete(dt, name):
	if not frappe.db.exists(dt, name):
		return {"success": False, "error": "Not found: %s" % name}
	frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
	return {"success": True}


def _gen_id(prefix):
	return "%s-%s%s" % (prefix, _b36(int(time.time() * 1000)), secrets.token_hex(2).upper())


def _b36(n):
	chars, s = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", ""
	while n:
		n, r = divmod(n, 36)
		s = chars[r] + s
	return s or "0"


def _next_num(dt, field, prefix):
	rows = frappe.db.sql(
		"select `%s` from `tab%s` where `%s` like %%s" % (field, dt, field), (prefix + "%",)
	)
	nums = []
	for (v,) in rows:
		try:
			nums.append(int(str(v)[len(prefix):]))
		except ValueError:
			pass
	return (max(nums) + 1) if nums else 1


def _area_code(road):
	if not road:
		return AREA_CODES["default"]
	key = road.lower().strip()
	for k, code in AREA_CODES.items():
		if k in key:
			return code
	return road.strip().split(" ")[0][:3].upper()


def _zone_for_road(road):
	if not road:
		return "Z-OUT-001"
	key = road.lower()
	for k, z in ZONE_ROAD_MAP.items():
		if k in key:
			return z
	return "Z-OUT-001"


def _digits(p):
	return re.sub(r"\D", "", str(p or ""))


def _last10(p):
	return _digits(p)[-10:]


def _is_admin(user=None):
	return bool(PRIVILEGED & set(frappe.get_roles(user or frappe.session.user)))


def _is_member(user=None):
	return bool((PRIVILEGED | {VOLUNTEER_ROLE}) & set(frappe.get_roles(user or frappe.session.user)))


def _settings_flag(field, default=1):
	v = frappe.db.get_single_value("Hasiruratha Settings", field)
	return default if v is None else cint(v)


# ════════════════════════════════════════════════════════════════════════════════════
#  the one endpoint the browser uses for data
# ════════════════════════════════════════════════════════════════════════════════════
ADMIN_ONLY = {"deleteSite", "deleteTree", "deleteVisit", "deleteVolunteer", "updateVolunteer", "assignTree", "getTreeReports", "createTreeReport", "assignTreeReport", "resolveTreeReport", "updateTreeReportStatus"}


@frappe.whitelist(methods=["POST"])
def call(action=None, data=None):
	"""Dispatcher — mirrors handleRequest() in the Apps Script."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in"), frappe.AuthenticationError)
	if not _is_member():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if isinstance(data, str):
		data = json.loads(data or "{}")
	p = data or {}

	handler = ACTIONS.get(action)
	if not handler:
		return {"success": False, "error": "Unknown action: %s" % action}
	if action in ADMIN_ONLY and not _is_admin():
		frappe.throw(_("Admin only"), frappe.PermissionError)

	try:
		return handler(p)
	except (frappe.PermissionError, frappe.AuthenticationError):
		raise
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Hasiruratha API: %s" % action)
		return {"success": False, "error": str(e)}


# ── zones ─────────────────────────────────────────────────────────────────────────────
def get_zones(p):
	f = {"active": 1}
	if p.get("group_id"):
		f["group_id"] = p["group_id"]
	return {"success": True, "data": _list("HR Zone", f)}


def get_zone_summary(p):
	gid = p.get("group_id") or GROUP
	zones = _list("HR Zone", {"group_id": gid, "active": 1})
	sites = frappe.get_all("HR Site", {"group_id": gid}, ["name", "zone_id"], limit_page_length=0)
	trees = frappe.get_all("HR Tree", {"group_id": gid}, ["site_id", "condition"], limit_page_length=0)
	visits = frappe.get_all("HR Visit", {"group_id": gid, "status": "Planned"}, ["site_id"], limit_page_length=0)

	site_zone = {s.name: s.zone_id for s in sites}
	out = []
	for z in zones:
		zid = z["zone_id"]
		zsites = {s.name for s in sites if s.zone_id == zid}
		ztrees = [t for t in trees if t.site_id in zsites]
		out.append({
			"zone_id": zid, "zone_name": z["zone_name"], "description": z["description"],
			"site_count": len(zsites), "tree_count": len(ztrees),
			"urgent": sum(1 for t in ztrees if t.condition == "Needs attention"),
			"planned": sum(1 for v in visits if site_zone.get(v.site_id) == zid),
		})
	return {"success": True, "data": out}


# ── sites ─────────────────────────────────────────────────────────────────────────────
def _site_filters(p):
	f = {}
	for k in ("group_id", "status", "zone_id"):
		if p.get(k):
			f[k] = p[k]
	return f


def get_sites(p):
	return {"success": True, "data": _list("HR Site", _site_filters(p))}


def get_sites_by_zone(p):
	if not p.get("zone_id"):
		return {"success": False, "error": "zone_id required"}
	f = {"zone_id": p["zone_id"], "group_id": p.get("group_id") or GROUP}
	return {"success": True, "data": _list("HR Site", f), "zone_id": p["zone_id"]}


LITE = ["site_id", "name", "road", "zone_id", "site_type", "gps_lat", "gps_lng",
        "gps_lat2", "gps_lng2", "status", "tree_count", "stretch_length"]


def get_sites_lite(p):
	f = {k: p[k] for k in ("group_id", "zone_id") if p.get(k)}
	return {"success": True, "data": [{k: (s.get(k) or None) for k in LITE} for s in _list("HR Site", f)]}


def add_site(b):
	code = _area_code(b.get("road"))
	site_id = "S-%s-%03d" % (code, _next_num("HR Site", "site_id", "S-%s-" % code))
	zone_id = b.get("zone_id") or _zone_for_road(b.get("road"))
	if not frappe.db.exists("HR Zone", zone_id):
		zone_id = None
	vals = _values("HR Site", b, skip=("site_id",))
	vals.update({
		"doctype": "HR Site", "site_id": site_id, "zone_id": zone_id,
		"group_id": b.get("group_id") or GROUP,
		"site_type": b.get("site_type") or "spot",
		"area": b.get("area") or b.get("road") or "",
		"tree_count": (cint(b.get("tree_count")) if (b.get("site_type") or "spot").lower() == "stretch" else (cint(b.get("tree_count")) or 1)),
		"status": b.get("status") or "Identified",
		"priority": b.get("priority") or "Medium",
		"date_added": getdate(b.get("date_added")) if b.get("date_added") else getdate(today()),
	})
	frappe.get_doc(vals).insert(ignore_permissions=True)
	return {"success": True, "site_id": site_id, "zone_id": zone_id}


def update_site(b):
	return _update("HR Site", b.get("site_id"), _values("HR Site", b, skip=("site_id",)))


def delete_site(p):
	"""Deletes the site AND its trees, tree conditions and visits (Frappe enforces links)."""
	sid = p.get("site_id")
	for dt in ("HR Condition", "HR Visit"):
		for n in frappe.get_all(dt, {"site_id": sid}, pluck="name"):
			frappe.delete_doc(dt, n, ignore_permissions=True, force=True)
	for n in frappe.get_all("HR Tree", {"site_id": sid}, pluck="name"):
		_delete_tree_cascade(n)
	return _delete("HR Site", sid)


# ── trees ─────────────────────────────────────────────────────────────────────────────
def get_trees(p):
	f = {}
	for k in ("group_id", "site_id", "status"):
		if p.get(k):
			f[k] = p[k]
	if p.get("owner_volunteer"):
		f["owner_volunteer_id"] = p["owner_volunteer"]
	data = _list("HR Tree", f)
	vol_ids = {t.get("owner_volunteer_id") for t in data if t.get("owner_volunteer_id")}
	vol_names = {}
	if vol_ids:
		for v in frappe.get_all("HR Volunteer", filters={"name": ["in", list(vol_ids)]}, fields=["name", "volunteer_name"]):
			vol_names[v.name] = v.volunteer_name
	for t in data:
		t["owner_volunteer_name"] = vol_names.get(t.get("owner_volunteer_id"), "")
		t["owner_volunteer"] = t["owner_volunteer_name"]
	return {"success": True, "data": data}


def get_my_trees(p):
	vid, name = p.get("volunteer_id"), (p.get("name") or "").lower()
	if not vid and not name:
		return {"success": True, "data": []}
	trees = [
		t for t in _list("HR Tree")
		if (vid and t.get("owner_volunteer_id") == vid)
		or (name and t.get("owner_volunteer_name") and t["owner_volunteer_name"].lower() == name)
	]
	site_names = {s.name: s.site_name for s in frappe.get_all("HR Site", fields=["name", "site_name"], limit_page_length=0)}
	for t in trees:
		t["site_name"] = site_names.get(t["site_id"], "")
	return {"success": True, "data": trees}


def get_trees_by_site(p):
	return {"success": True, "data": _list("HR Tree", {"site_id": p.get("site_id")})}


def _tree_doc(b, tree_id, position, defaults=None):
	d = defaults or {}
	vals = _values("HR Tree", b, skip=("tree_id",))
	vals.update({
		"doctype": "HR Tree", "tree_id": tree_id,
		"site_id": b.get("site_id") or d.get("site_id") or None,
		"group_id": b.get("group_id") or d.get("group_id") or GROUP,
		"position": cint(position),
		"tree_guard": b.get("tree_guard") or d.get("tree_guard") or "No",
		"support_pole": b.get("support_pole") or d.get("support_pole") or "No",
		"condition": b.get("condition") or "Unknown",
		"status": b.get("status") or d.get("status") or "Identified",
		"date_planted": getdate(b.get("date_planted") or d.get("date_planted") or today()),
		"last_reported": getdate(today()),
	})
	for k in ("species", "owner_volunteer_id", "planted_by", "photo_url", "notes", "gps_lat", "gps_lng"):
		if k not in vals and d.get(k) not in (None, ""):
			vals[k] = d[k]
	# Admins / Frappe users are not HR Volunteers. Never save an owner that does not exist
	# (this caused: Could not find Owner: Administrator).
	owner = vals.get("owner_volunteer_id")
	if owner and not frappe.db.exists("HR Volunteer", owner):
		vals.pop("owner_volunteer_id", None)
	return frappe.get_doc(vals)


def add_tree(b):
	code = _area_code(b.get("road") or b.get("area") or "")
	tree_id = "HR-%s-%04d" % (code, _next_num("HR Tree", "tree_id", "HR-%s-" % code))
	_tree_doc(b, tree_id, b.get("position") or 1).insert(ignore_permissions=True)
	return {"success": True, "tree_id": tree_id}


def add_trees_bulk(b):
	trees = b.get("trees") or []
	if isinstance(trees, str):
		trees = json.loads(trees)
	code = _area_code(b.get("road") or "")
	start = _next_num("HR Tree", "tree_id", "HR-%s-" % code)
	ids = []
	for idx, t in enumerate(trees):
		tree_id = "HR-%s-%04d" % (code, start + idx)
		merged = dict(t)
		merged.setdefault("site_id", b.get("site_id"))
		_tree_doc(merged, tree_id, t.get("position") or idx + 1, defaults=b).insert(ignore_permissions=True)
		ids.append(tree_id)
	if b.get("site_id"):
		_update("HR Site", b["site_id"], {"tree_count": len(trees)})
	return {"success": True, "tree_ids": ids, "count": len(ids)}


def update_tree(b):
	vals = _values("HR Tree", b, skip=("tree_id",))
	vals["last_reported"] = getdate(today())
	return _update("HR Tree", b.get("tree_id"), vals)


def _delete_tree_cascade(tree_id):
	for n in frappe.get_all("HR Condition", {"tree_id": tree_id}, pluck="name"):
		frappe.delete_doc("HR Condition", n, ignore_permissions=True, force=True)
	return _delete("HR Tree", tree_id)


def delete_tree(p):
	return _delete_tree_cascade(p.get("tree_id"))


# ── visits ────────────────────────────────────────────────────────────────────────────
def get_visits(p):
	f = {}
	for k in ("group_id", "site_id", "status"):
		if p.get(k):
			f[k] = p[k]
	if p.get("zone_id"):
		ids = frappe.get_all("HR Site", {"zone_id": p["zone_id"]}, pluck="name")
		f["site_id"] = ["in", ids or ["__none__"]]
	data = _list("HR Visit", f)
	data.sort(key=lambda v: v.get("planned_date") or "")
	return {"success": True, "data": data}


def add_visit(b):
	visit_id = _gen_id("V")
	vals = _values("HR Visit", b, skip=("visit_id",))
	vals.update({
		"doctype": "HR Visit", "visit_id": visit_id,
		"group_id": b.get("group_id") or GROUP,
		"planned_time": b.get("planned_time") or "06:30",
		"volunteers_needed": cint(b.get("volunteers_needed")) or 2,
		"status": b.get("status") or "Planned",
	})
	frappe.get_doc(vals).insert(ignore_permissions=True)
	if b.get("site_id") and b.get("planned_date"):
		_update("HR Site", b["site_id"], {"status": "Planned"})
	return {"success": True, "visit_id": visit_id}


def update_visit(b):
	return _update("HR Visit", b.get("visit_id"), _values("HR Visit", b, skip=("visit_id",)))


def join_visit(b):
	if not frappe.db.exists("HR Visit", b.get("visit_id")):
		return {"success": False, "error": "Visit not found"}
	cur = frappe.db.get_value("HR Visit", b["visit_id"], "willing_to_join") or ""
	names = [n.strip() for n in cur.split(",") if n.strip()]
	if b.get("name") and b["name"] not in names:
		names.append(b["name"])
	frappe.db.set_value("HR Visit", b["visit_id"], "willing_to_join", ", ".join(names))
	return {"success": True, "joining": names}


def delete_visit(p):
	return _delete("HR Visit", p.get("visit_id"))


# ── conditions ────────────────────────────────────────────────────────────────────────
def get_conditions(p):
	f = {k: p[k] for k in ("tree_id", "site_id") if p.get(k)}
	data = _list("HR Condition", f)
	data.sort(key=lambda c: c.get("date") or "", reverse=True)
	return {"success": True, "data": data}


def add_condition(b):
	cid = _gen_id("C")
	vals = _values("HR Condition", b, skip=("condition_id", "resolved", "resolved_date"))
	vals.update({
		"doctype": "HR Condition", "condition_id": cid,
		"date": getdate(b.get("date") or today()),
		"tree_id": b.get("tree_id") or None, "site_id": b.get("site_id") or None,
	})
	frappe.get_doc(vals).insert(ignore_permissions=True)
	if b.get("tree_id"):
		urgent = any(_coerce(frappe._dict(fieldtype="Check"), b.get(k)) for k in ("watering_needed", "dead", "guard_damaged"))
		if _coerce(frappe._dict(fieldtype="Check"), b.get("dead")):
			cond = "Dead"
		elif _coerce(frappe._dict(fieldtype="Check"), b.get("healthy")):
			cond = "Healthy"
		else:
			cond = "Needs attention" if urgent else "Monitored"
		_update("HR Tree", b["tree_id"], {"condition": cond, "last_reported": getdate(today())})
	return {"success": True, "condition_id": cid}


def resolve_condition(b):
	return _update("HR Condition", b.get("condition_id"), {"resolved": 1, "resolved_date": getdate(today())})


# ── volunteers ────────────────────────────────────────────────────────────────────────
def _mask_phone(phone):
	d = _digits(phone)
	if not d:
		return None
	return d[:5] + " •••••" if len(d) >= 10 else "••••• •••••"


def _mask_email(email):
	if not email or "@" not in email:
		return email
	local, domain = email.split("@", 1)
	return email if len(local) <= 3 else local[:3] + "•••@" + domain


def get_volunteers(p):
	f = {}
	if p.get("group_id"):
		f["group_id"] = p["group_id"]
	if p.get("zone_id"):
		f["primary_zone_id"] = p["zone_id"]
	data = _list("HR Volunteer", f)
	if not _is_admin():
		# contact details are masked on the SERVER for volunteers, not just hidden in the UI
		for v in data:
			v["phone"], v["email"] = _mask_phone(v["phone"]), _mask_email(v["email"])
	return {"success": True, "data": data}


def update_volunteer(b):
	return _update("HR Volunteer", b.get("volunteer_id"), _values("HR Volunteer", b, skip=("volunteer_id", "user")))


def delete_volunteer(p):
	vid = p.get("volunteer_id")
	user = frappe.db.get_value("HR Volunteer", vid, "user")
	res = _delete("HR Volunteer", vid)
	if user and frappe.db.exists("User", user) and not (PRIVILEGED & set(frappe.get_roles(user))):
		frappe.db.set_value("User", user, "enabled", 0)
	return res


def _sync_volunteer_tree_list(volunteer_id):
	if not volunteer_id or not frappe.db.exists("HR Volunteer", volunteer_id):
		return
	tree_ids = frappe.get_all("HR Tree", filters={"owner_volunteer_id": volunteer_id}, pluck="tree_id", limit_page_length=0)
	frappe.db.set_value("HR Volunteer", volunteer_id, "trees_owned", ", ".join(sorted(x for x in tree_ids if x)))


def assign_tree(b):
	tree_id, vid = b.get("tree_id"), b.get("volunteer_id")
	if not tree_id:
		return {"success": False, "error": "Tree ID is required"}
	tree_name = frappe.db.get_value("HR Tree", {"tree_id": tree_id}, "name")
	if not tree_name:
		return {"success": False, "error": "Tree not found"}
	if not vid or not frappe.db.exists("HR Volunteer", vid):
		return {"success": False, "error": "Volunteer not found"}
	vol = frappe.db.get_value("HR Volunteer", vid, ["active", "group_id"], as_dict=True)
	tree = frappe.db.get_value("HR Tree", tree_name, ["group_id", "owner_volunteer_id"], as_dict=True)
	if not cint(vol.active):
		return {"success": False, "error": "This volunteer is inactive"}
	if vol.group_id and tree.group_id and vol.group_id != tree.group_id:
		return {"success": False, "error": "Volunteer and tree belong to different groups"}
	old_vid = tree.owner_volunteer_id
	frappe.db.set_value("HR Tree", tree_name, "owner_volunteer_id", vid)
	_sync_volunteer_tree_list(old_vid)
	_sync_volunteer_tree_list(vid)
	return {"success": True, "tree_id": tree_id, "volunteer_id": vid,
	        "volunteer_name": frappe.db.get_value("HR Volunteer", vid, "volunteer_name")}


def get_tree_reports(p):
	filters = {k: p[k] for k in ("tree_id", "site_id", "status", "group_id") if p.get(k)}
	rows = frappe.get_all("HR Tree Report", filters=filters,
	 fields=["name", "report_id", "tree_id", "site_id", "zone_id", "group_id", "reported_by",
	         "reported_on", "issue_type", "description", "priority", "status", "photo_url",
	         "gps_lat", "gps_lng", "assigned_volunteer_id", "assigned_volunteer_name",
	         "resolution_notes", "resolved_on"],
	 order_by="reported_on desc, modified desc", limit_page_length=500)
	return {"success": True, "data": rows}


def create_tree_report(b):
	tree_id = (b.get("tree_id") or "").strip()
	if not tree_id:
		return {"success": False, "error": "Select an existing tree. A report never creates a tree."}
	tree_name = frappe.db.get_value("HR Tree", {"tree_id": tree_id}, "name")
	if not tree_name:
		return {"success": False, "error": "Selected tree was not found"}
	tree = frappe.get_doc("HR Tree", tree_name)
	site_id = tree.site_id
	if b.get("site_id") and b.get("site_id") != site_id:
		return {"success": False, "error": "Selected site does not match this tree"}
	site = frappe.get_doc("HR Site", site_id) if site_id else None
	if not (b.get("description") or b.get("issue_type")):
		return {"success": False, "error": "Add an issue type or description"}
	report_id = _gen_id("TR")
	doc = frappe.get_doc({"doctype": "HR Tree Report", "report_id": report_id,
	 "tree_id": tree.name, "site_id": site_id, "zone_id": site.zone_id if site else None,
	 "group_id": tree.group_id or (site.group_id if site else GROUP),
	 "reported_by": frappe.session.user, "reported_on": getdate(today()),
	 "issue_type": b.get("issue_type") or "Other", "description": b.get("description") or "",
	 "priority": b.get("priority") or "Medium", "status": "Open",
	 "photo_url": b.get("photo_url") or "",
	 "gps_lat": flt(b.get("gps_lat")) if b.get("gps_lat") not in (None, "") else None,
	 "gps_lng": flt(b.get("gps_lng")) if b.get("gps_lng") not in (None, "") else None})
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("HR Tree", tree.name, "last_reported", getdate(today()))
	return {"success": True, "report_id": report_id, "name": doc.name}


def assign_tree_report(b):
	doc = frappe.get_doc("HR Tree Report", b.get("report_id"))
	vid = b.get("volunteer_id")
	if not vid or not frappe.db.exists("HR Volunteer", vid):
		return {"success": False, "error": "Volunteer not found"}
	vol = frappe.db.get_value("HR Volunteer", vid, ["active", "group_id", "volunteer_name"], as_dict=True)
	if not cint(vol.active):
		return {"success": False, "error": "This volunteer is inactive"}
	if vol.group_id and doc.group_id and vol.group_id != doc.group_id:
		return {"success": False, "error": "Volunteer and report belong to different groups"}
	doc.assigned_volunteer_id = vid
	doc.assigned_volunteer_name = vol.volunteer_name
	doc.status = "Assigned"
	doc.save(ignore_permissions=True)
	return {"success": True, "report_id": doc.report_id, "volunteer_name": vol.volunteer_name}


def update_tree_report_status(b):
	doc = frappe.get_doc("HR Tree Report", b.get("report_id"))
	allowed = {"Open", "Acknowledged", "Assigned", "In Progress", "On Hold", "Resolved"}
	status = (b.get("status") or "").strip()
	if status not in allowed:
		return {"success": False, "error": "Choose a valid report status"}
	if status == "Assigned" and not doc.assigned_volunteer_id:
		return {"success": False, "error": "Assign a volunteer before setting the report to Assigned"}
	doc.status = status
	if status == "Resolved":
		doc.resolved_on = getdate(today())
		doc.resolution_notes = b.get("resolution_notes") or doc.resolution_notes
	else:
		doc.resolved_on = None
	doc.save(ignore_permissions=True)
	return {"success": True, "report_id": doc.report_id, "status": doc.status}


def resolve_tree_report(b):
	doc = frappe.get_doc("HR Tree Report", b.get("report_id"))
	doc.status = "Resolved"
	doc.resolution_notes = b.get("resolution_notes") or doc.resolution_notes
	doc.resolved_on = getdate(today())
	doc.save(ignore_permissions=True)
	return {"success": True, "report_id": doc.report_id, "status": doc.status}


# ── dashboards ────────────────────────────────────────────────────────────────────────
def _urgent_cond(c):
	return c.watering_needed or c.dead or c.guard_damaged


def get_dashboard(p):
	gid = p.get("group_id") or GROUP
	sites = frappe.get_all("HR Site", {"group_id": gid}, ["status"], limit_page_length=0)
	trees = frappe.get_all("HR Tree", {"group_id": gid}, ["condition", "owner_volunteer_id"], limit_page_length=0)
	vols = frappe.get_all("HR Volunteer", {"group_id": gid}, ["active"], limit_page_length=0)
	conds = frappe.get_all("HR Condition", {"resolved": 0}, ["tree_id", "watering_needed", "dead", "guard_damaged"], limit_page_length=0)
	visits = _list("HR Visit", {"group_id": gid, "status": "Planned"})
	visits.sort(key=lambda v: v.get("planned_date") or "")
	count = lambda status: sum(1 for s in sites if s.status == status)
	return {"success": True, "data": {
		"total_trees": len(trees), "total_sites": len(sites),
		"identified": count("Identified"), "planned": count("Planned"),
		"completed": count("Completed"), "monitoring": count("Monitoring"),
		"urgent": len({c.tree_id for c in conds if _urgent_cond(c)}),
		"healthy": sum(1 for t in trees if t.condition == "Healthy"),
		"active_volunteers": sum(1 for v in vols if cint(v.active)),
		"unowned_trees": sum(1 for t in trees if not t.owner_volunteer_id),
		"planned_visits": visits[:5],
	}}


def get_dashboard_stats(p):
	"""
	NOTE: this action exists in the live app but was missing from the Apps Script file we were
	given, so the shape is inferred from renderAdminDashboard()/updateStatusStrip() in the
	frontend. Definitions marked (*) are best guesses - confirm against the live numbers.
	"""
	gid = p.get("group_id") or GROUP
	zones = _list("HR Zone", {"group_id": gid, "active": 1})
	sites = frappe.get_all("HR Site", {"group_id": gid}, ["name", "zone_id", "site_type", "status", "gps_lat", "gps_lng"], limit_page_length=0)
	trees = frappe.get_all("HR Tree", {"group_id": gid}, ["site_id"], limit_page_length=0)
	vols = frappe.get_all("HR Volunteer", {"group_id": gid}, ["active"], limit_page_length=0)
	conds = frappe.get_all(
		"HR Condition", fields=["site_id", "resolved", "watering_needed", "dead", "guard_damaged", "guard_removal_needed"],
		limit_page_length=0,
	)
	no_gps = lambda s: not (flt(s.gps_lat) and flt(s.gps_lng))
	open_urgent = [c for c in conds if not cint(c.resolved) and _urgent_cond(c)]          # (*)
	site_zone = {s.name: s.zone_id for s in sites}

	zrows = []
	for z in zones:
		zid = z["zone_id"]
		zs = {s.name for s in sites if s.zone_id == zid}
		zrows.append({
			"zone_id": zid, "zone_name": z["zone_name"], "site_count": len(zs),
			"tree_count": sum(1 for t in trees if t.site_id in zs),
			"completed_count": sum(1 for s in sites if s.zone_id == zid and s.status == "Completed"),
			"urgent_count": sum(1 for c in open_urgent if site_zone.get(c.site_id) == zid),
			"no_gps_count": sum(1 for s in sites if s.zone_id == zid and no_gps(s)),
		})
	return {"success": True, "totals": {
		"total_trees": len(trees),
		"urgent_requests": len(open_urgent),                                              # (*)
		"completed_requests": sum(1 for c in conds if cint(c.resolved)),                  # (*)
		"volunteer_count": sum(1 for v in vols if cint(v.active)),
		"guard_removal_pending": sum(1 for c in conds if cint(c.guard_removal_needed) and not cint(c.resolved)),
		"guard_removal_done": sum(1 for c in conds if cint(c.guard_removal_needed) and cint(c.resolved)),
		"total_sites": len(sites),
		"total_stretches": sum(1 for s in sites if (s.site_type or "").lower() == "stretch"),
		"total_spots": sum(1 for s in sites if (s.site_type or "").lower() == "spot"),
		"missing_gps": sum(1 for s in sites if no_gps(s)),
	}, "zones": zrows}


# ════════════════════════════════════════════════════════════════════════════════════
#  GEOLOCATION: reverse geocoding (lat/lng -> road + area) — runs on the SERVER
#  (the device GPS itself is read in the browser with navigator.geolocation)
# ════════════════════════════════════════════════════════════════════════════════════
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def reverse_geocode(p):
	try:
		lat, lng = float(p.get("lat")), float(p.get("lng"))
	except (TypeError, ValueError):
		return {"success": False, "error": "Bad coordinates"}
	if not (-90 <= lat <= 90 and -180 <= lng <= 180):
		return {"success": False, "error": "Bad coordinates"}

	# cache by ~11 m grid so repeated taps don't burn Google quota (same idea as the Apps Script)
	key = "hr_rg_%.4f_%.4f" % (lat, lng)
	hit = _cache().get_value(key)
	if hit:
		return hit

	# per-user throttle: 60 lookups / minute
	rl = "hr_rg_rl_%s_%s" % (frappe.local.site, frappe.session.user)
	cache = _cache()
	n = cache.incrby(rl, 1)
	if n == 1:
		cache.expire(rl, 60)
	if n > 60:
		return {"success": False, "error": "Too many lookups, wait a minute"}

	from frappe.utils.password import get_decrypted_password
	api_key = get_decrypted_password(
		"Hasiruratha Settings", "Hasiruratha Settings", "google_maps_server_key", raise_exception=False
	)
	if not api_key:
		return {"success": False, "error": "Geocoding key not configured in Hasiruratha Settings"}

	import requests
	try:
		r = requests.get(
			GEOCODE_URL,
			params={"latlng": "%s,%s" % (lat, lng), "key": api_key, "language": "en", "region": "in"},
			timeout=8,
		)
		res = r.json()
	except Exception as e:
		return {"success": False, "error": "Geocoder unreachable: %s" % e}
	if res.get("status") != "OK" or not res.get("results"):
		return {"success": False, "error": res.get("status") or "NO_RESULT"}

	road = area = ""
	for result in res["results"]:
		for c in result.get("address_components", []):
			types = c.get("types", [])
			if not road and "route" in types:
				road = c["long_name"]
			if not area and any(t in types for t in ("sublocality_level_1", "sublocality", "neighborhood")):
				area = c["long_name"]
		if road and area:
			break
	out = {"success": True, "road": road or area, "area": area, "address": res["results"][0].get("formatted_address")}
	_cache().set_value(key, out, expires_in_sec=6 * 3600)
	return out


# ════════════════════════════════════════════════════════════════════════════════════
#  photos: Frappe File instead of Cloudflare Worker -> Google Drive
# ════════════════════════════════════════════════════════════════════════════════════
MAX_PHOTO_BYTES = 6 * 1024 * 1024


@frappe.whitelist(methods=["POST"])
def upload_photo(base64_data=None, filename=None, zone_name=None):
	if frappe.session.user == "Guest" or not _is_member():
		frappe.throw(_("Please sign in"), frappe.AuthenticationError)
	if not base64_data:
		return {"success": False, "error": "No image data provided"}
	try:
		raw = base64.b64decode(re.sub(r"^data:image/\w+;base64,", "", base64_data))
	except Exception:
		return {"success": False, "error": "Bad image data"}
	if len(raw) > MAX_PHOTO_BYTES:
		return {"success": False, "error": "Photo too large"}
	if not raw.startswith(b"\xff\xd8\xff"):               # the app always sends JPEG
		return {"success": False, "error": "Only JPEG photos are accepted"}

	safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "photo_%d.jpg" % int(time.time()))[:120]
	if not safe.lower().endswith((".jpg", ".jpeg")):
		safe += ".jpg"
	f = frappe.get_doc({
		"doctype": "File", "file_name": safe, "content": raw, "is_private": 0,
	}).insert(ignore_permissions=True)
	return {"success": True, "url": f.file_url, "file_id": f.name}


# ════════════════════════════════════════════════════════════════════════════════════
#  sign-in: mobile number -> real Frappe session
#  Volunteers get a low-privilege Website User (role HR Volunteer, no desk access).
#  Admins sign in with the normal Frappe login page (roles: HR Admin / System Manager).
# ════════════════════════════════════════════════════════════════════════════════════
def _find_volunteer(phone):
	want = _last10(phone)
	if len(want) < 10:
		return None
	for v in frappe.get_all("HR Volunteer", fields=["name", "phone", "active", "user", "volunteer_name"], limit_page_length=0):
		if _last10(v.phone) == want:
			return v
	return None


def _ensure_user(vol):
	if vol.user and frappe.db.exists("User", vol.user):
		return vol.user
	email = "v%s@volunteer.hasiruratha.local" % _last10(vol.phone)
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": vol.volunteer_name or "Volunteer",
			"enabled": 1, "user_type": "Website User", "send_welcome_email": 0,
			"new_password": secrets.token_urlsafe(24),
			"roles": [{"role": VOLUNTEER_ROLE}],
		}).insert(ignore_permissions=True)
	frappe.db.set_value("HR Volunteer", vol.name, "user", email)
	return email


def _login_as(user):
	if PRIVILEGED & set(frappe.get_roles(user)):
		# a mobile number must never open an admin account
		frappe.throw(_("This account must sign in with the admin login"), frappe.PermissionError)
	if not cint(frappe.db.get_value("User", user, "enabled")):
		frappe.throw(_("Account disabled"), frappe.PermissionError)
	frappe.local.login_manager.login_as(user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=300)
def login_phone(phone=None):
	if not _settings_flag("allow_phone_login"):
		return {"success": False, "error": "Mobile sign-in is turned off"}
	vol = _find_volunteer(phone)
	if not vol:
		return {"success": True, "found": False}
	if not cint(vol.active):
		return {"success": False, "error": "This volunteer account is inactive"}
	_login_as(_ensure_user(vol))
	return {"success": True, "found": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def register_phone(name=None, phone=None, email=None, area=None, group_id=None):
	if not _settings_flag("allow_self_registration"):
		return {"success": False, "error": "Registration is closed. Ask an admin to add you."}
	name = (name or "").strip()
	phone = _digits(phone)
	if not name or len(phone) < 10:
		return {"success": False, "error": "Name and a valid 10-digit mobile number required"}
	if _find_volunteer(phone):
		return {"success": False, "error": "Already registered. Please sign in."}
	vid = _gen_id("VOL")
	frappe.get_doc({
		"doctype": "HR Volunteer", "volunteer_id": vid, "volunteer_name": name, "phone": phone,
		"email": (email or "").strip(), "area": (area or "").strip(),
		"group_id": group_id or GROUP, "joined_date": getdate(today()), "active": 1,
	}).insert(ignore_permissions=True)
	vol = _find_volunteer(phone)
	_login_as(_ensure_user(vol))
	return {"success": True, "volunteer_id": vid}


def build_boot():
	"""What the page needs to know about the signed-in person (injected by the renderer)."""
	user = frappe.session.user
	if user == "Guest" or not _is_member(user):
		return {"logged_in": False}
	admin = _is_admin(user)
	row = frappe.db.get_value("HR Volunteer", {"user": user}, ["name"] + _cols("HR Volunteer"), as_dict=True)
	if row:
		u = _ser("HR Volunteer", row)
	else:
		u = {"volunteer_id": user, "name": frappe.utils.get_fullname(user), "phone": "", "email": user,
		     "primary_zone_id": None, "group_id": GROUP}
	u["role"] = "admin" if admin else "volunteer"
	return {"logged_in": True, "user": u}


# ── action table ──────────────────────────────────────────────────────────────────────
ACTIONS = {
	"getZones": get_zones, "getZoneSummary": get_zone_summary,
	"getSites": get_sites, "getSitesByZone": get_sites_by_zone, "getSitesLite": get_sites_lite,
	"addSite": add_site, "updateSite": update_site, "deleteSite": delete_site,
	"getTrees": get_trees, "getMyTrees": get_my_trees, "getTreesBySite": get_trees_by_site,
	"addTree": add_tree, "addTreesBulk": add_trees_bulk, "updateTree": update_tree, "deleteTree": delete_tree,
	"getVisits": get_visits, "addVisit": add_visit, "updateVisit": update_visit,
	"joinVisit": join_visit, "deleteVisit": delete_visit,
	"getConditions": get_conditions, "addCondition": add_condition, "resolveCondition": resolve_condition,
	"getTreeReports": get_tree_reports, "createTreeReport": create_tree_report,
	"assignTreeReport": assign_tree_report, "resolveTreeReport": resolve_tree_report, "updateTreeReportStatus": update_tree_report_status,
	"getVolunteers": get_volunteers, "updateVolunteer": update_volunteer,
	"deleteVolunteer": delete_volunteer, "assignTree": assign_tree,
	"getDashboard": get_dashboard, "getDashboardStats": get_dashboard_stats,
	"reverseGeocode": reverse_geocode,
}
