import frappe

from hasiruratha import citizen_api as ca

no_cache = 1

TREE_MSG = {"Identified": "Recorded. Our team will visit soon.", "Planned": "A care visit is planned.",
            "Completed": "Planted. Thank you! 🌱", "Healthy": "Growing well 🌿", "Monitoring": "Our volunteers are keeping an eye on it.",
            "Urgent": "Needs urgent care. Our team has been told.", "Hold": "On hold for now."}
STEPS = ["Open", "Acknowledged", "Assigned", "In Progress", "Resolved"]
STEP_LABELS = ["Received", "Seen", "Volunteer", "In progress", "Resolved"]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/citizen-login?redirect-to=/my-status"
		raise frappe.Redirect
	context.no_breadcrumbs = True
	s = ca.my_status()
	context.s = s
	for t in s["trees"]:
		t["msg"] = TREE_MSG.get(t["status"], "")
	for r in s["reports"]:
		r["step"] = STEPS.index(r["status"]) if r["status"] in STEPS else -1
	context.steps = STEP_LABELS
	context.resolved = len([r for r in s["reports"] if r["status"] == "Resolved"])
	context.requests = frappe.get_all("HR Volunteer Request", {"owner": frappe.session.user}, ["name", "status", "creation"], order_by="creation desc")
