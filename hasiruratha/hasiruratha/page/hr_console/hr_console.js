// Hasiru Ratha Console: admin actions, live map and duplicate review in one Desk page.
const HRC = "hasiruratha.hasiruratha.page.hr_console.hr_console";
const HR_SITE = "hasiruratha.hasiruratha.doctype.hr_site.hr_site";
const LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/";
const COLORS = { "Needs Review": "#f97316", Urgent: "#dc2626", Completed: "#16a34a", Healthy: "#16a34a",
	Monitoring: "#7c3aed", Planned: "#2563eb", Identified: "#eab308", Hold: "#6b7280" };

frappe.pages["hr-console"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Hasiru Ratha Console"), single_column: true });
	wrapper.hrc = new HRConsole(page, wrapper);
};
frappe.pages["hr-console"].on_page_show = function (wrapper) { wrapper.hrc && wrapper.hrc.load(); };

class HRConsole {
	constructor(page, wrapper) {
		this.page = page; this.data = null; this.map = null;
		page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");
		$(page.body).html(`
		<style>
		.hrc{padding:4px 0 24px}.hrc-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
		.hrc-tile{background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:16px;cursor:pointer;text-align:left}
		.hrc-tile:hover{box-shadow:var(--shadow-md)}.hrc-tile b{display:block;font-size:15px;margin:6px 0 2px}.hrc-tile small{color:var(--text-muted)}
		.hrc-ico{font-size:22px}.hrc-badge{float:right;background:#f97316;color:#fff;border-radius:10px;padding:0 8px;font-size:12px;font-weight:600}
		.hrc-main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:16px}
		.hrc-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:12px}
		#hrc-map{height:520px;border-radius:8px;z-index:0}.hrc-legend span{display:inline-block;margin:6px 10px 0 0;font-size:12px}
		.hrc-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
		.hrc-q{border:1px solid var(--border-color);border-radius:10px;padding:10px;margin-bottom:10px}
		.hrc-q .btn{margin:6px 6px 0 0}.hrc-empty{color:var(--text-muted);padding:12px 0}
		@media(max-width:900px){.hrc-main{grid-template-columns:1fr}#hrc-map{height:55vh}}
		</style>
		<div class="hrc">
		 <div class="hrc-tiles">
		  <div class="hrc-tile" data-act="plant"><span class="hrc-ico">🌱</span><b>${__("Plant a sapling")}</b><small>${__("Opens the planting screen")}</small></div>
		  <div class="hrc-tile" data-act="report"><span class="hrc-ico">📝</span><b>${__("Report a tree")}</b><small>${__("Tell us what a tree needs")}</small></div>
		  <div class="hrc-tile" data-act="visit"><span class="hrc-ico">📅</span><b>${__("Plan a visit")}</b><small>${__("Schedule a care visit")}</small></div>
		  <div class="hrc-tile" data-act="assign"><span class="hrc-ico">🤝</span><b>${__("Assign a volunteer")}</b><small>${__("To a tree or a report")}</small></div>
		  <div class="hrc-tile" data-act="dups"><span class="hrc-ico">🔎</span><b>${__("Review duplicates")}<span class="hrc-badge" id="hrc-badge" style="display:none"></span></b><small>${__("Same spot entered twice?")}</small></div>
		 </div>
		 <div class="hrc-main">
		  <div class="hrc-card"><div id="hrc-map"></div><div class="hrc-legend" id="hrc-legend"></div></div>
		  <div class="hrc-card" id="hrc-dups"><h5>${__("Possible duplicates")}</h5><div id="hrc-queue"></div></div>
		 </div>
		</div>`);
		const $b = $(page.body);
		$b.on("click", "[data-act]", (e) => this.act($(e.currentTarget).data("act"), $(e.currentTarget).data("site")));
		$b.on("click", "[data-q]", (e) => this.review($(e.currentTarget).data("q"), $(e.currentTarget).data("name"), $(e.currentTarget).data("other")));
		frappe.require([LEAFLET + "leaflet.css", LEAFLET + "leaflet.js"], () => { this.leafletReady = true; this.draw(); });
	}

	load() {
		frappe.xcall(`${HRC}.get_console_data`).then((d) => { this.data = d; this.render(); this.draw(); });
	}

	render() {
		const n = this.data.counts.review, $bd = $("#hrc-badge");
		n ? $bd.text(n).show() : $bd.hide();
		const q = this.data.queue.map((x) => `
			<div class="hrc-q"><b>${frappe.utils.escape_html(x.site_name || x.site_id)}</b>
			<div class="text-muted small">${__("is close to")} <a href="/app/hr-site/${x.other_id}">${frappe.utils.escape_html(x.other_name || x.other_id)}</a>${x.distance_m != null ? ` · ${x.distance_m} m` : ""}</div>
			<button class="btn btn-xs btn-default" data-q="approve" data-name="${x.site_id}">${__("Different site")}</button>
			<button class="btn btn-xs btn-primary" data-q="merge" data-name="${x.site_id}" data-other="${x.other_id}">${__("Same place - merge")}</button>
			<a class="btn btn-xs btn-link" href="/app/hr-site/${x.site_id}">${__("Open")}</a></div>`).join("");
		$("#hrc-queue").html(q || `<div class="hrc-empty">${__("Nothing to review. New sites close to an existing one will show up here.")}</div>`);
	}

	draw() {
		if (!this.leafletReady || !this.data) return;
		if (!this.map) {
			this.map = L.map("hrc-map").setView([12.97, 77.59], 11);
			L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(this.map);
			this.layer = L.layerGroup().addTo(this.map);
			$("#hrc-legend").html(Object.entries(COLORS).map(([k, c]) => `<span><i class="hrc-dot" style="background:${c}"></i>${__(k)}</span>`).join(""));
		}
		this.layer.clearLayers();
		const pts = [];
		this.data.sites.forEach((s) => {
			if (!s.gps_lat || !s.gps_lng) return;
			const c = COLORS[s.status] || "#6b7280", e = frappe.utils.escape_html;
			L.circleMarker([s.gps_lat, s.gps_lng], { radius: s.status === "Needs Review" ? 11 : 8, color: "#fff", weight: 2, fillColor: c, fillOpacity: 0.95 })
				.bindPopup(`<b>${e(s.site_name || s.site_id)}</b><br>${e(s.road || s.area || "")}<br>${s.tree_count || 0} ${__("trees")} · ${__(s.status)}<br>
				<a href="/app/hr-site/${s.name}">${__("Open")}</a> · <a href="#" data-act="visit" data-site="${s.name}">${__("Plan a visit")}</a>`)
				.addTo(this.layer);
			pts.push([s.gps_lat, s.gps_lng]);
		});
		if (pts.length) this.map.fitBounds(pts, { padding: [30, 30], maxZoom: 17 });
		setTimeout(() => this.map.invalidateSize(), 200);
	}

	act(a, site) {
		if (a === "plant") return window.open("/hasiruratha", "_blank");
		if (a === "dups") return $("#hrc-dups")[0].scrollIntoView({ behavior: "smooth" });
		if (!this.data) return frappe.show_alert(__("Still loading, try again in a moment"));
		if (a === "report") return this.reportDialog();
		if (a === "visit") return this.visitDialog(site);
		if (a === "assign") return this.assignDialog();
	}

	opts(rows, f) { return rows.map(f); }

	reportDialog() {
		const d = new frappe.ui.Dialog({
			title: __("Report a tree"),
			fields: [
				{ fieldname: "tree_id", fieldtype: "Autocomplete", label: __("Tree"), reqd: 1,
				  options: this.opts(this.data.trees, (t) => ({ label: `${t.tree_id} · ${t.species || ""} · ${t.site_id}`, value: t.tree_id })) },
				{ fieldname: "issue_type", fieldtype: "Select", label: __("What does it need?"), reqd: 1,
				  options: "Damage\nWatering\nPest / Disease\nDead tree\nGuard / Support\nDebris\nLeaning\nOther", default: "Watering" },
				{ fieldname: "priority", fieldtype: "Select", label: __("Priority"), options: "Low\nMedium\nHigh\nCritical", default: "Medium" },
				{ fieldname: "description", fieldtype: "Small Text", label: __("Notes") },
			],
			primary_action_label: __("Send"),
			primary_action: (v) => frappe.xcall(`${HRC}.report_tree`, v).then(() => { d.hide(); frappe.show_alert({ message: __("Report saved"), indicator: "green" }); }),
		});
		d.show();
	}

	visitDialog(site) {
		const d = new frappe.ui.Dialog({
			title: __("Plan a visit"),
			fields: [
				{ fieldname: "site_id", fieldtype: "Autocomplete", label: __("Site"), reqd: 1, default: site || "",
				  options: this.opts(this.data.sites, (s) => ({ label: `${s.site_name || s.name} (${s.name})`, value: s.name })) },
				{ fieldname: "planned_date", fieldtype: "Date", label: __("Date"), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: "planned_time", fieldtype: "Data", label: __("Time"), default: "06:30" },
				{ fieldname: "service_type", fieldtype: "Select", label: __("What will volunteers do?"),
				  options: "Watering / follow-up\nNew plantation\nMaintenance visit\nTree Guard Needed\nTree Guard Removal\nSupport pole needed\nPesticide needed\nDebris cleanup", default: "Watering / follow-up" },
				{ fieldname: "volunteers_needed", fieldtype: "Int", label: __("Volunteers needed"), default: 2 },
			],
			primary_action_label: __("Plan visit"),
			primary_action: (v) => frappe.xcall(`${HRC}.plan_visit`, v).then(() => { d.hide(); frappe.show_alert({ message: __("Visit planned"), indicator: "green" }); this.load(); }),
		});
		d.show();
	}

	assignDialog() {
		const d = new frappe.ui.Dialog({
			title: __("Assign a volunteer"),
			fields: [
				{ fieldname: "mode", fieldtype: "Select", label: __("Assign to"), options: "A tree\nA tree report", default: "A tree" },
				{ fieldname: "tree_id", fieldtype: "Autocomplete", label: __("Tree"), depends_on: "eval:doc.mode=='A tree'", mandatory_depends_on: "eval:doc.mode=='A tree'",
				  options: this.opts(this.data.trees, (t) => ({ label: `${t.tree_id} · ${t.species || ""} · ${t.site_id}${t.owner_volunteer_id ? " · " + t.owner_volunteer_id : ""}`, value: t.tree_id })) },
				{ fieldname: "report_id", fieldtype: "Autocomplete", label: __("Report"), depends_on: "eval:doc.mode=='A tree report'", mandatory_depends_on: "eval:doc.mode=='A tree report'",
				  options: this.opts(this.data.reports, (r) => ({ label: `${r.report_id} · ${r.tree_id} · ${r.issue_type} (${r.status})`, value: r.report_id })) },
				{ fieldname: "volunteer_id", fieldtype: "Autocomplete", label: __("Volunteer"), reqd: 1,
				  options: this.opts(this.data.volunteers, (v) => ({ label: `${v.volunteer_name} (${v.volunteer_id})`, value: v.volunteer_id })) },
			],
			primary_action_label: __("Assign"),
			primary_action: (v) => frappe.xcall(`${HRC}.assign`, {
				tree_id: v.mode === "A tree" ? v.tree_id : null, report_id: v.mode === "A tree report" ? v.report_id : null, volunteer_id: v.volunteer_id,
			}).then(() => { d.hide(); frappe.show_alert({ message: __("Volunteer assigned"), indicator: "green" }); this.load(); }),
		});
		d.show();
	}

	review(kind, name, other) {
		const go = () => frappe.xcall(`${HR_SITE}.${kind === "merge" ? "merge_site" : "approve_site"}`, { name }).then(() => this.load());
		kind === "merge"
			? frappe.confirm(__("Move all trees, visits and reports of {0} to {1} and mark it Merged?", [name, other]), go)
			: go();
	}
}
