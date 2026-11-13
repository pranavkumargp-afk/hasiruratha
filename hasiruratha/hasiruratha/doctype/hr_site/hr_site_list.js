frappe.listview_settings["HR Site"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const c = { "Needs Review": "orange", Merged: "gray", Urgent: "red", Completed: "green",
			Monitoring: "purple", Planned: "blue", Identified: "yellow", Hold: "gray" };
		return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
	},
};
