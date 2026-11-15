import frappe

no_cache = 1


def get_context(context):
	context.no_breadcrumbs = True
	context.title = "Sign in"
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/citizen-home"
		raise frappe.Redirect
