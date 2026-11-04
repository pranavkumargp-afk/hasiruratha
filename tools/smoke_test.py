# End-to-end smoke test (44 checks). Needs a running dev server: bench --site hasiruratha.localhost serve --port 8000
# and an Administrator password of "admin". Creates test volunteers/sites. Run: python tools/smoke_test.py
import requests, json, re, base64, sys
B = "http://127.0.0.1:8000"; HOST = {"Host": "hasiruratha.localhost"}
TINY = base64.b64decode('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AJQAB/9k=')
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  PASS", name)
    else: fail += 1; print("  FAIL", name, extra)

def S():
    s = requests.Session(); s.headers.update(HOST); return s
def boot(s):
    r = s.get(B + "/hasiruratha")
    m = re.search(r'window\.HR_BOOT = (\{.*?\});</script>', r.text, re.S)
    return json.loads(m.group(1)), r
def call(s, csrf, action, **data):
    r = s.post(B + "/api/method/hasiruratha.api.call", data={"action": action, "data": json.dumps(data)},
               headers={"X-Frappe-CSRF-Token": csrf})
    try: return r.status_code, r.json().get("message")
    except Exception: return r.status_code, None

print("== 1. guest page"); g = S(); b, r = boot(g)
check("page 200", r.status_code == 200); check("guest not logged in", b["logged_in"] is False)
check("no leftover placeholders", "__HR_BOOT__" not in r.text and "__GMAPS_KEY__" not in r.text)
check("no old Apps Script / worker / key", not any(x in r.text for x in ("script.google.com", "workers.dev", "AIza")))
check("map callback present", "onMapsReady" in r.text)
check("cache-control no-store", r.headers.get("Cache-Control") == "no-store")
st, _ = call(g, "", "getSites"); check("guest cannot call API", st in (401, 403), st)

print("== 2. admin"); a = S()
lr = a.post(B + "/api/method/login", data={"usr": "Administrator", "pwd": "admin"}); check("admin login", lr.status_code == 200, lr.text[:100])
ab, _ = boot(a); csrf = ab.get("csrf_token", "")
check("boot admin", ab["logged_in"] and ab["user"]["role"] == "admin"); check("csrf present", len(csrf) > 10)
st, r1 = call(a, csrf, "addSite", name="Kanakapura Metro", road="Kanakapura Road", gps_lat="12.8806", gps_lng=77.5731, added_by="Tester", notes="demo")
check("addSite", r1 and r1.get("success") and r1["site_id"] == "S-KAN-001" and r1["zone_id"] == "Z-KAN-001", r1)
sid = r1["site_id"]
st, r2 = call(a, csrf, "addTreesBulk", site_id=sid, road="Kanakapura Road", planted_by="Tester",
              trees=[{"species": "Neem", "position": 1, "tree_guard": "Yes"}, {"species": "Pongamia", "position": 2}, {"species": "Neem", "position": 3}])
check("addTreesBulk ids sequential", r2 and r2["tree_ids"] == ["HR-KAN-0001", "HR-KAN-0002", "HR-KAN-0003"], r2)
st, r3 = call(a, csrf, "getSitesByZone", zone_id="Z-KAN-001", group_id="GRP-001")
site = r3["data"][0]
check("site shape (name/gps/tree_count)", site["name"] == "Kanakapura Metro" and site["gps_lat"] == 12.8806 and site["tree_count"] == 3 and site["site_id"] == sid, site)
check("empty fields are null like the Sheet", site["gps_lat2"] is None and site["stretch_length"] is None, site)
st, r4 = call(a, csrf, "addCondition", tree_id="HR-KAN-0001", site_id=sid, reported_by="Tester", watering_needed=True)
st, t = call(a, csrf, "getTreesBySite", site_id=sid)
check("condition marks tree urgent", [x for x in t["data"] if x["tree_id"] == "HR-KAN-0001"][0]["condition"] == "Needs attention")
st, d = call(a, csrf, "getDashboard", group_id="GRP-001"); check("dashboard counts", d["data"]["total_trees"] == 3 and d["data"]["urgent"] == 1 and d["data"]["total_sites"] == 1, d)
st, ds = call(a, csrf, "getDashboardStats", group_id="GRP-001")
check("dashboardStats shape", ds["success"] and ds["totals"]["total_trees"] == 3 and ds["totals"]["urgent_requests"] == 1 and ds["totals"]["missing_gps"] == 0 and any(z["zone_id"] == "Z-KAN-001" and z["tree_count"] == 3 for z in ds["zones"]), ds)
st, zs = call(a, csrf, "getZoneSummary", group_id="GRP-001")
check("zone summary", [z for z in zs["data"] if z["zone_id"] == "Z-KAN-001"][0]["tree_count"] == 3 and [z for z in zs["data"] if z["zone_id"] == "Z-KAN-001"][0]["urgent"] == 1)
st, v = call(a, csrf, "addVisit", site_id=sid, group_id="GRP-001", planned_date="2026-11-02", planned_by="Admin", service_type="Watering")
check("addVisit + site becomes Planned", v["success"] and call(a, csrf, "getSites", status="Planned")[1]["data"][0]["site_id"] == sid)
vid = v["visit_id"]
st, jv = call(a, csrf, "joinVisit", visit_id=vid, name="Asha"); check("joinVisit", jv["joining"] == ["Asha"])
st, bad = call(a, csrf, "bogusAction"); check("unknown action reported", bad["success"] is False)

print("== 3. volunteer self-registration + session"); v = S()
rr = v.post(B + "/api/method/hasiruratha.api.register_phone", data={"name": "Asha K", "phone": "98450 12345", "email": "asha@example.com", "area": "JP Nagar"})
check("register ok (no csrf for guest)", rr.status_code == 200 and rr.json()["message"].get("success"), rr.text[:200])
vb, _ = boot(v); vcsrf = vb.get("csrf_token", "")
check("boot volunteer", vb["logged_in"] and vb["user"]["role"] == "volunteer" and vb["user"]["name"] == "Asha K", vb)
st, z = call(v, vcsrf, "getZoneSummary"); check("volunteer reads zones", st == 200 and z["success"])
st, _ = call(v, vcsrf, "deleteSite", site_id=sid); check("volunteer cannot deleteSite", st == 403, st)
st, _ = call(v, vcsrf, "updateVolunteer", volunteer_id=vb["user"]["volunteer_id"], name="Hacked"); check("volunteer cannot updateVolunteer", st == 403, st)
st, us = call(v, vcsrf, "updateSite", site_id=sid, name="Renamed by volunteer"); check("volunteer can update a site (rename key)", us["success"] and call(v, vcsrf, "getSites")[1]["data"][0]["name"] == "Renamed by volunteer")
# a second volunteer so masking has something to hide
v2 = S(); v2.post(B + "/api/method/hasiruratha.api.register_phone", data={"name": "Ravi", "phone": "9000011111", "email": "ravi@example.com"})
st, vols = call(v, vcsrf, "getVolunteers"); ravi = [x for x in vols["data"] if x["name"] == "Ravi"][0]
check("volunteer sees MASKED contact for others (server-side)", "•" in ravi["phone"] and "•" in ravi["email"] and "11111" not in ravi["phone"], ravi)
st, avols = call(a, csrf, "getVolunteers"); ravi_a = [x for x in avols["data"] if x["name"] == "Ravi"][0]
check("admin sees full contact", ravi_a["phone"] == "9000011111" and ravi_a["email"] == "ravi@example.com", ravi_a)
rest = v.get(B + "/api/resource/HR Volunteer"); check("volunteer blocked from REST /api/resource", rest.status_code in (401, 403), rest.status_code)
rest2 = v.get(B + "/api/resource/HR Site"); check("volunteer blocked from REST HR Site", rest2.status_code in (401, 403), rest2.status_code)
dup = S().post(B + "/api/method/hasiruratha.api.register_phone", data={"name": "Asha again", "phone": "+91 9845012345"})
check("duplicate phone (+91 variant) rejected", dup.json()["message"].get("success") is False, dup.text[:150])

print("== 4. phone login"); l = S()
r_ok = l.post(B + "/api/method/hasiruratha.api.login_phone", data={"phone": "9845012345"}); check("known number logs in", r_ok.json()["message"] == {"success": True, "found": True}, r_ok.text)
lb, _ = boot(l); check("session is volunteer Asha", lb["logged_in"] and lb["user"]["name"] == "Asha K")
r_no = S().post(B + "/api/method/hasiruratha.api.login_phone", data={"phone": "7777777777"}); check("unknown number -> found False", r_no.json()["message"] == {"success": True, "found": False})
# admin-takeover guard: link a volunteer record to the Administrator user, then try its phone
import subprocess
open("/home/frappe/mkadmin.py", "w").write('''exec(open('/home/frappe/fx.py').read())
frappe.get_doc({"doctype":"HR Volunteer","volunteer_id":"VOL-ADM","volunteer_name":"Admin Vol","phone":"8888888888","user":"Administrator","active":1}).insert(ignore_permissions=True)
frappe.db.commit()
''')
subprocess.run("cd /home/frappe/fbench/sites && ../env/bin/python /home/frappe/mkadmin.py", shell=True, capture_output=True)
ra = S(); rr2 = ra.post(B + "/api/method/hasiruratha.api.login_phone", data={"phone": "8888888888"})
bb, _ = boot(ra); check("mobile number can NEVER open an admin account", bb["logged_in"] is False and rr2.status_code == 403, (rr2.status_code, bb))

print("== 5. photo upload"); b64 = base64.b64encode(TINY).decode()
up = v.post(B + "/api/method/hasiruratha.api.upload_photo", data={"base64_data": "data:image/jpeg;base64," + b64, "filename": "S-KAN-001_site_2026-10-27.jpg", "zone_name": "Kanakapura"}, headers={"X-Frappe-CSRF-Token": vcsrf})
um = up.json()["message"]; check("upload ok", um["success"] and um["url"].startswith("/files/"), um)
fr = requests.get(B + um["url"], headers=HOST); check("photo is publicly viewable", fr.status_code == 200 and fr.content == TINY, fr.status_code)
bad = v.post(B + "/api/method/hasiruratha.api.upload_photo", data={"base64_data": base64.b64encode(b"<script>alert(1)</script>").decode(), "filename": "x.jpg"}, headers={"X-Frappe-CSRF-Token": vcsrf})
check("non-JPEG rejected", bad.json()["message"]["success"] is False)
gu = S().post(B + "/api/method/hasiruratha.api.upload_photo", data={"base64_data": b64})
check("guest cannot upload", gu.status_code in (401, 403), gu.status_code)
st, ph = call(v, vcsrf, "updateSite", site_id=sid, photo_url=um["url"]); check("photo url stored on site", ph["success"])

print("== 6. reverse geocode (no key configured yet)")
st, rg = call(v, vcsrf, "reverseGeocode", lat=12.85806, lng=77.65299); check("clean error without key", rg["success"] is False and "not configured" in rg["error"], rg)
st, rg2 = call(v, vcsrf, "reverseGeocode", lat="abc", lng=1); check("bad coordinates rejected", rg2["success"] is False)

print("== 7. cascade delete (admin)")
st, dt = call(a, csrf, "deleteSite", site_id=sid); check("deleteSite cascades", dt["success"] and call(a, csrf, "getTrees")[1]["data"] == [] and call(a, csrf, "getVisits")[1]["data"] == [])
print(f"\nRESULT: {ok} passed, {fail} failed"); sys.exit(1 if fail else 0)
