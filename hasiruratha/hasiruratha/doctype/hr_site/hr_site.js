// Admin review of possible duplicate sites, using Frappe's own form UI.
const HR_SITE = "hasiruratha.hasiruratha.doctype.hr_site.hr_site";
const LF = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/";

function hr_card(title, s, color) {
	const e = frappe.utils.escape_html;
	if (!s) return `<div class="col-sm-6"><div class="text-muted">${title}: ${__("not found")}</div></div>`;
	return `<div class="col-sm-6" style="margin-bottom:10px"><div style="border:2px solid ${color};border-radius:10px;overflow:hidden">
		${s.photo ? `<a href="${e(s.photo)}" target="_blank"><img src="${e(s.photo)}" style="width:100%;height:180px;object-fit:cover"></a>` : `<div style="height:180px;display:flex;align-items:center;justify-content:center;background:#f3f4f6" class="text-muted">${__("No photo")}</div>`}
		<div style="padding:8px 10px"><b>${title}</b>: <a href="/app/hr-site/${s.name}">${e(s.site_name || s.name)}</a><br>
		<span class="text-muted small">${e([s.road, s.area].filter(Boolean).join(", "))} · ${s.tree_count || 0} ${__("trees")} · ${e(s.status || "")}</span></div></div></div>`;
}

function hr_dup_panel(frm) {
	const f = frm.fields_dict.duplicate_map;
	if (!f || !frm.doc.possible_duplicate_of) return;
	f.$wrapper.html(`<div class="row" id="hr-dupcards"></div><div id="hr-dupmap" style="height:320px;border-radius:8px;margin:6px 0"></div><div class="text-muted small" id="hr-dupinfo"></div>`);
	frappe.xcall(`${HR_SITE}.duplicate_info`, { name: frm.doc.name }).then((r) => {
		$("#hr-dupcards").html(hr_card(__("This site"), r.this, "#f97316") + hr_card(__("Possible duplicate"), r.other, "#2563eb"));
		const a = r.this, o = r.other;
		if (!a || !o || !a.gps_lat || !o.gps_lat) return;
		frappe.require([LF + "leaflet.css", LF + "leaflet.js"], () => {
			const map = L.map("hr-dupmap"), here = [frm.doc.gps_lat || a.gps_lat, frm.doc.gps_lng || a.gps_lng], there = [o.gps_lat, o.gps_lng];
			L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
			const mk = L.marker(here, { draggable: true }).addTo(map).bindTooltip(__("This site (drag to move)"), { permanent: true, direction: "top" });
			L.circleMarker(there, { radius: 11, color: "#fff", weight: 2, fillColor: "#2563eb", fillOpacity: 0.95 }).addTo(map)
				.bindTooltip(frm.doc.possible_duplicate_of, { permanent: true, direction: "bottom" });
			const line = L.polyline([here, there], { color: "#f97316", dashArray: "6 6" }).addTo(map);
			const info = () => $("#hr-dupinfo").text(__("Distance between the two: {0} m", [Math.round(map.distance(mk.getLatLng(), there))]));
			map.fitBounds([here, there], { padding: [50, 50], maxZoom: 19 }); info();
			mk.on("drag", () => { line.setLatLngs([mk.getLatLng(), there]); info(); });
			mk.on("dragend", () => {
				const p = mk.getLatLng(); frm.set_value("gps_lat", p.lat); frm.set_value("gps_lng", p.lng);
				frappe.show_alert({ message: __("Location moved. Save to keep it."), indicator: "orange" });
			});
		});
	});
}

frappe.ui.form.on("HR Site", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.possible_duplicate_of) return;
		hr_dup_panel(frm);
		if (frm.doc.status !== "Needs Review") return;
		const other = frm.doc.possible_duplicate_of;
		frm.dashboard.set_headline_alert(
			__("This is a possible duplicate of <a href='/app/hr-site/{0}'><b>{0}</b></a>. Compare the photos below.", [other]), "orange");
		frm.add_custom_button(__("Different site - keep it"), () =>
			frappe.xcall(`${HR_SITE}.approve_site`, { name: frm.doc.name }).then(() => frm.reload_doc()), __("Review"));
		frm.add_custom_button(__("Same place - merge"), () =>
			frappe.confirm(__("Move all trees, visits and reports to {0} and mark this site Merged?", [other]), () =>
				frappe.xcall(`${HR_SITE}.merge_site`, { name: frm.doc.name }).then(() => frm.reload_doc())), __("Review"));
		frm.add_custom_button(__("Delete duplicate"), () => hr_delete_dialog(frm.doc.name, other, () => frappe.set_route("List", "HR Site")), __("Review"));
		frm.page.set_inner_btn_group_as_primary(__("Review"));
	},
});

function hr_delete_dialog(name, other, done) {
	frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", reqd: 1, label: __("Why is this a duplicate?"),
		description: __("Trees and records of this site move to {0}. A full copy is kept in HR Deleted Site.", [other]) },
		(v) => frappe.xcall(`${HR_SITE}.delete_duplicate`, { name, reason: v.reason }).then(() => {
			frappe.show_alert({ message: __("Deleted. A copy is in HR Deleted Site."), indicator: "green" }); done && done();
		}), __("Delete duplicate site {0}", [name]), __("Delete"));
}
window.hr_delete_dialog = hr_delete_dialog;
