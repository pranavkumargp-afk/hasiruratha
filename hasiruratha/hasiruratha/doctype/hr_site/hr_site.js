// Admin review of possible duplicate sites, using Frappe's own form UI.
const HR_SITE = "hasiruratha.hasiruratha.doctype.hr_site.hr_site";

frappe.ui.form.on("HR Site", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Needs Review" || !frm.doc.possible_duplicate_of) return;
		const other = frm.doc.possible_duplicate_of;
		frm.dashboard.set_headline_alert(
			__("This site is very close to <a href='/app/hr-site/{0}'><b>{0}</b></a>. Is it the same place?", [other]),
			"orange"
		);
		frm.add_custom_button(__("Different site - keep it"), () =>
			frappe.xcall(`${HR_SITE}.approve_site`, { name: frm.doc.name }).then(() => frm.reload_doc()),
			__("Review"));
		frm.add_custom_button(__("Same place - merge"), () =>
			frappe.confirm(__("Move all trees, visits and reports to {0} and mark this site Merged?", [other]), () =>
				frappe.xcall(`${HR_SITE}.merge_site`, { name: frm.doc.name }).then(() => frm.reload_doc())),
			__("Review"));
		frm.page.set_inner_btn_group_as_primary(__("Review"));
	},
});
