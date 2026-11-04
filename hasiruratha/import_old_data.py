"""
Import data exported from the old site into the Frappe DocTypes.

Put your export at  sites/old_data.json  (inside frappe-bench) like this:
{
  "zones":      [ {...}, {...} ],
  "sites":      [ {...} ],
  "trees":      [ {...} ],
  "volunteers": [ {...} ]
}
Each key inside a record is matched to a DocType field by fieldname OR label
(case and spaces ignored). Keys with no match are skipped and printed at the end.

Run:  bench --site hasiru-ratha.localhost execute hasiruratha.import_old_data.run
"""
import json
import re

import frappe

ORDER = [("zones", "HR Zone"), ("sites", "HR Site"), ("trees", "HR Tree"), ("volunteers", "HR Volunteer")]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def run():
    path = frappe.get_site_path("..", "old_data.json")
    data = json.load(open(path, encoding="utf-8"))
    skipped = {}
    for key, doctype in ORDER:
        meta = frappe.get_meta(doctype)
        lookup = {}
        for f in meta.fields:
            lookup[norm(f.fieldname)] = f.fieldname
            lookup[norm(f.label)] = f.fieldname
        made = 0
        for rec in data.get(key, []):
            doc = {"doctype": doctype}
            for k, v in rec.items():
                fn = lookup.get(norm(k))
                if fn and v not in (None, ""):
                    doc[fn] = v
                elif not fn:
                    skipped.setdefault(doctype, set()).add(k)
            try:
                frappe.get_doc(doc).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
                made += 1
            except Exception as e:
                print(f"  ! {doctype} {rec.get('name') or rec}: {e}")
        frappe.db.commit()
        print(f"{doctype}: imported {made} of {len(data.get(key, []))}")
    for dt, keys in skipped.items():
        print(f"Not matched in {dt}: {sorted(keys)}")
