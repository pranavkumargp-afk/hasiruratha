const CIT = "hasiruratha.citizen_api.review_application";
frappe.ui.form.on("HR Application", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Pending" || frm.doc.application_type !== "Volunteer Application") return;
		if (frm.doc.email_verified) frm.dashboard.set_headline_alert(__("Email verified by code"), "green");
		frm.add_custom_button(__("Approve volunteer"), () =>
			frappe.xcall(CIT, { name: frm.doc.name, approve: 1 }).then(() => frm.reload_doc()), __("Review"));
		frm.add_custom_button(__("Reject"), () =>
			frappe.prompt({ fieldname: "notes", fieldtype: "Small Text", label: __("Reason (optional)") }, (v) =>
				frappe.xcall(CIT, { name: frm.doc.name, approve: 0, notes: v.notes }).then(() => frm.reload_doc()), __("Reject application")),
			__("Review"));
		frm.page.set_inner_btn_group_as_primary(__("Review"));
	},
});
