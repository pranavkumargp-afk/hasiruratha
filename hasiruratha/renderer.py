# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt
"""
Serves the single-page volunteer app at /hasiruratha.

The page is a plain HTML file (templates/app.html). We only fill in three things per request:
  __HR_BOOT__     who is signed in + the CSRF token (JSON)
  __GMAPS_KEY__   Google Maps JavaScript key from "Hasiruratha Settings" (never hard-coded in the repo)
"""
import json
import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

ROUTES = {"hasiruratha", "hasiruratha/index"}
_TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "app.html")
_cached = {"mtime": 0, "html": ""}


def _template():
	m = os.path.getmtime(_TEMPLATE)
	if m != _cached["mtime"]:
		with open(_TEMPLATE, encoding="utf-8") as f:
			_cached.update(mtime=m, html=f.read())
	return _cached["html"]


class HasirurathaRenderer(BaseRenderer):
	def can_render(self):
		return (self.path or "").strip("/ ") in ROUTES

	def render(self):
		from hasiruratha.api import build_boot

		boot = build_boot()
		try:
			boot["csrf_token"] = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
		except Exception:
			boot["csrf_token"] = ""
		maps_key = frappe.db.get_single_value("Hasiruratha Settings", "google_maps_browser_key") or ""

		blob = json.dumps(boot).replace("</", "<\\/")
		html = _template().replace("__HR_BOOT__", blob).replace("__GMAPS_KEY__", maps_key)

		resp = Response(html, status=200, content_type="text/html; charset=utf-8")
		resp.headers["Cache-Control"] = "no-store"
		return resp
