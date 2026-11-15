frappe.listview_settings["HR Citizen Report"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const c = {"Received":"orange","Seen":"blue","Volunteer assigned":"blue","In progress":"purple","On hold":"gray","Resolved":"green"};
		return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
	},
};
