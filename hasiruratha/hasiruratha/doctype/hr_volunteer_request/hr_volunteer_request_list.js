frappe.listview_settings["HR Volunteer Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const c = {"Pending":"orange","Approved":"green","Rejected":"red"};
		return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
	},
};
