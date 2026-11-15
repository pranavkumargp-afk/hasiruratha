frappe.listview_settings["HR Citizen Planting"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const c = {"Received":"orange","On the map":"green","Needs a check":"red"};
		return [__(doc.status), c[doc.status] || "gray", "status,=," + doc.status];
	},
};
