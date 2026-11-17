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
		this.page = page; this.data = null; this.map = null; this.f = { q: "", zone: "", show: "both", issue: "", status: "" };
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
		.hrc-filters{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:center}
		@media(max-width:900px){.hrc-filters{grid-template-columns:1fr 1fr}.hrc-filters #hrc-q{grid-column:1/-1}}
		.hrc-c{display:flex;gap:12px;border:1px solid var(--border-color);border-radius:10px;padding:10px;margin-bottom:10px}
		.hrc-c img{width:84px;height:84px;object-fit:cover;border-radius:8px;flex:none;background:#eee}
		.hrc-c .body{flex:1;min-width:0}.hrc-c select{max-width:200px;display:inline-block}.hrc-tag{font-size:11px;border-radius:6px;padding:1px 6px;margin-right:6px;color:#fff}
		@media(max-width:600px){.hrc-c{flex-direction:column}.hrc-c img{width:100%;height:160px}}
		.hrc-q .btn{margin:6px 6px 0 0}.hrc-empty{color:var(--text-muted);padding:12px 0}
		@media(max-width:900px){.hrc-main{grid-template-columns:1fr}#hrc-map{height:55vh}}
		</style>
		<div class="hrc">
		 <div class="hrc-tiles">
		  <div class="hrc-tile" data-act="plant"><span class="hrc-ico">🌱</span><b>${__("Plant a sapling")}</b><small>${__("Opens the planting screen")}</small></div>
		  <div class="hrc-tile" data-act="report"><span class="hrc-ico">📝</span><b>${__("Report a tree")}</b><small>${__("Tell us what a tree needs")}</small></div>
		  <div class="hrc-tile" data-act="visit"><span class="hrc-ico">📅</span><b>${__("Plan a visit")}</b><small>${__("Schedule a care visit")}</small></div>
		  <div class="hrc-tile" data-act="assign"><span class="hrc-ico">🤝</span><b>${__("Assign a volunteer")}</b><small>${__("To a tree or a report")}</small></div>
		  <div class="hrc-tile" data-act="citizen"><span class="hrc-ico">🧑‍🌾</span><b>${__("Citizen submissions")}<span class="hrc-badge" id="hrc-cbadge" style="display:none"></span></b><small>${__("New plantings and reports")}</small></div>
		  <div class="hrc-tile" data-act="dups"><span class="hrc-ico">🔎</span><b>${__("Review duplicates")}<span class="hrc-badge" id="hrc-badge" style="display:none"></span></b><small>${__("Same spot entered twice?")}</small></div>
		 </div>
		 <div class="hrc-main">
		  <div class="hrc-card">
		   <div class="hrc-filters"><input class="form-control" id="hrc-q" placeholder="${__("Search area or road, e.g. Electronic City")}">
		    <select class="form-control" id="hrc-zone"><option value="">${__("All zones")}</option></select>
		    <select class="form-control" id="hrc-show"><option value="both">${__("Sites + reports")}</option><option value="reports">${__("Reports only")}</option><option value="sites">${__("Sites only")}</option></select>
		    <select class="form-control" id="hrc-issue"><option value="">${__("All issues")}</option>${["Dead tree", "Damage", "Watering", "Pest / Disease", "Leaning", "Debris", "Guard / Support", "Other"].map((x) => `<option>${x}</option>`).join("")}</select>
		    <select class="form-control" id="hrc-status"><option value="">${__("Any status")}</option>${["Open", "Acknowledged", "Assigned", "In Progress", "On Hold"].map((x) => `<option>${x}</option>`).join("")}</select>
		    <button class="btn btn-xs btn-default" id="hrc-clear">${__("Clear")}</button></div>
		   <div class="small text-muted" id="hrc-sum" style="margin-bottom:8px"></div><div id="hrc-map"></div><div class="hrc-legend" id="hrc-legend"></div></div>
		  <div class="hrc-card" id="hrc-dups"><h5>${__("Possible duplicates")}</h5><div id="hrc-queue"></div></div>
		 </div>
		 <div class="hrc-card" id="hrc-cit" style="margin-top:16px"><h5>${__("Citizen submissions to review")}</h5><div id="hrc-citlist"></div></div>
		</div>`);
		const $b = $(page.body);
		const refilter = () => { this.draw(); this.renderCitizen(); };
		let tm;
		$b.on("input", "#hrc-q", (e) => { this.f.q = e.target.value; clearTimeout(tm); tm = setTimeout(refilter, 250); });
		$b.on("change", "#hrc-zone,#hrc-show,#hrc-issue,#hrc-status", () => {
			Object.assign(this.f, { zone: $("#hrc-zone").val(), show: $("#hrc-show").val(), issue: $("#hrc-issue").val(), status: $("#hrc-status").val() }); refilter();
		});
		$b.on("click", "#hrc-clear", () => {
			this.f = { q: "", zone: "", show: "both", issue: "", status: "" };
			$("#hrc-q").val(""); $("#hrc-zone,#hrc-issue,#hrc-status").val(""); $("#hrc-show").val("both"); refilter();
		});
		$b.on("click", "[data-act]", (e) => this.act($(e.currentTarget).data("act"), $(e.currentTarget).data("site"), $(e.currentTarget).data("rep")));
		$b.on("click", "[data-cr]", (e) => {
			const i = $(e.currentTarget).data("cr"), c = this.data.citizen[i], z = $(`[data-zone=${i}]`).val();
			frappe.xcall("hasiruratha.citizen_api.admin_review", { kind: c.kind, name: c.name, zone_id: z }).then(() => { frappe.show_alert({ message: __("Confirmed"), indicator: "green" }); this.load(); });
		});
		$b.on("click", "[data-cmap]", (e) => {
			const c = this.data.citizen[$(e.currentTarget).data("cmap")];
			if (this.map && c.lat) { this.map.setView([c.lat, c.lng], 18); $("#hrc-map")[0].scrollIntoView({ behavior: "smooth" }); }
		});
		$b.on("click", "[data-q]", (e) => this.review($(e.currentTarget).data("q"), $(e.currentTarget).data("name"), $(e.currentTarget).data("other")));
		frappe.require([LEAFLET + "leaflet.css", LEAFLET + "leaflet.js"], () => { this.leafletReady = true; this.draw(); });
	}

	load() {
		frappe.xcall(`${HRC}.get_console_data`).then((d) => { this.data = d; this.render(); this.draw(); });
	}

	render() {
		const zsel = $("#hrc-zone"), keep = zsel.val();
		zsel.html(`<option value="">${__("All zones")}</option>` + (this.data.zones || []).map((z) => `<option value="${z.zone_id}">${frappe.utils.escape_html(z.zone_name)}</option>`).join("")).val(keep || "");
		const n = this.data.counts.review, $bd = $("#hrc-badge");
		n ? $bd.text(n).show() : $bd.hide();
		const q = this.data.queue.map((x) => `
			<div class="hrc-q"><b>${frappe.utils.escape_html(x.site_name || x.site_id)}</b>
			<div class="text-muted small">${__("is close to")} <a href="/app/hr-site/${x.other_id}">${frappe.utils.escape_html(x.other_name || x.other_id)}</a>${x.distance_m != null ? ` · ${x.distance_m} m` : ""}</div>
			<button class="btn btn-xs btn-default" data-q="approve" data-name="${x.site_id}">${__("Different site")}</button>
			<button class="btn btn-xs btn-primary" data-q="merge" data-name="${x.site_id}" data-other="${x.other_id}">${__("Same place - merge")}</button>
			<button class="btn btn-xs btn-danger" data-q="delete" data-name="${x.site_id}" data-other="${x.other_id}">${__("Delete duplicate")}</button>
			<a class="btn btn-xs btn-link" href="/app/hr-site/${x.site_id}">${__("Open")}</a></div>`).join("");
		const cn = (this.data.citizen || []).length, $cb = $("#hrc-cbadge");
		cn ? $cb.text(cn).show() : $cb.hide();
		this.renderCitizen();
		$("#hrc-queue").html(q || `<div class="hrc-empty">${__("Nothing to review. New sites close to an existing one will show up here.")}</div>`);
	}

	renderCitizen() {
		const e = frappe.utils.escape_html, zones = this.data.zones || [];
		const rows = (this.data.citizen || []).filter((c) => this.pass([c.area, c.road, c.address], c.zone_id)).map((c) => {
			const i = this.data.citizen.indexOf(c);
			const opts = zones.map((z) => `<option value="${z.zone_id}" ${z.zone_id === c.zone_id ? "selected" : ""}>${e(z.zone_name)}</option>`).join("");
			return `<div class="hrc-c">
			  ${c.photo_url ? `<a href="${e(c.photo_url)}" target="_blank"><img src="${e(c.photo_url)}"></a>` : "<img>"}
			  <div class="body"><span class="hrc-tag" style="background:${c.kind === "Plant" ? "#16a34a" : "#f97316"}">${c.kind === "Plant" ? __("Plant") : __("Report")}</span><b>${e(c.title)}</b>
			  <div class="text-muted small">${e([c.road, c.area].filter(Boolean).join(", ") || c.address || "")}</div>
			  <div class="text-muted small">${e(c.address || "")}</div>
			  <div class="small">${__("By")} ${e(c.by)}${c.phone ? " · " + e(c.phone) : ""} · ${frappe.datetime.prettyDate(c.when)}${c.detail ? " · " + e(c.detail) : ""}</div>
			  <div class="small text-muted">${e(c.zone_note || "")}</div>
			  <div style="margin-top:6px"><label class="small">${__("Zone")} </label> <select class="form-control input-xs" data-zone="${i}">${opts}</select>
			  <button class="btn btn-xs btn-primary" data-cr="${i}">${__("Confirm")}</button>
			  ${c.lat ? `<button class="btn btn-xs btn-default" data-cmap="${i}">${__("On map")}</button>` : ""}
			  <button class="btn btn-xs btn-default" data-act="visit" data-site="${c.site_id || ""}">${__("Plan a visit")}</button>
			  ${c.site_id ? `<a class="btn btn-xs btn-link" href="/app/hr-site/${c.site_id}">${__("Open site")}</a>` : ""}</div></div></div>`;
		}).join("");
		$("#hrc-citlist").html(rows || `<div class="hrc-empty">${__("No new citizen submissions.")}</div>`);
	}

	pass(texts, zone) {
		const f = this.f, q = (f.q || "").toLowerCase().trim();
		if (f.zone && zone !== f.zone) return false;
		return !q || texts.some((t) => (t || "").toLowerCase().includes(q));
	}

	draw() {
		if (!this.leafletReady || !this.data) return;
		const e = frappe.utils.escape_html, zn = {};
		(this.data.zones || []).forEach((z) => (zn[z.zone_id] = z.zone_name));
		if (!this.map) {
			this.map = L.map("hrc-map").setView([12.97, 77.59], 11);
			L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(this.map);
			this.layer = L.layerGroup().addTo(this.map);
			$("#hrc-legend").html(Object.entries(COLORS).map(([k, c]) => `<span><i class="hrc-dot" style="background:${c}"></i>${__(k)}</span>`).join("")
				+ `<br><span><i class="hrc-dot" style="background:#dc2626;border:2px solid #111"></i>${__("Report: high")}</span><span><i class="hrc-dot" style="background:#f97316;border:2px solid #111"></i>${__("medium")}</span><span><i class="hrc-dot" style="background:#2563eb;border:2px solid #111"></i>${__("low")}</span>`);
		}
		this.layer.clearLayers();
		const f = this.f, pts = [], zones = new Set();
		let ns = 0, nr = 0;
		if (f.show !== "reports" && !f.issue && !f.status) {
			this.data.sites.forEach((s) => {
				if (!s.gps_lat || !s.gps_lng || !this.pass([s.area, s.road, s.site_name, s.name], s.zone_id)) return;
				const c = COLORS[s.status] || "#6b7280";
				L.circleMarker([s.gps_lat, s.gps_lng], { radius: s.status === "Needs Review" ? 11 : 8, color: "#fff", weight: 2, fillColor: c, fillOpacity: 0.95 })
					.bindPopup(`<b>${e(s.site_name || s.site_id)}</b><br>${e(s.area || s.road || "")}<br>${e(zn[s.zone_id] || "")}<br>${s.tree_count || 0} ${__("trees")} · ${__(s.status)}<br>
					<a href="/app/hr-site/${s.name}">${__("Open")}</a> · <a href="#" data-act="visit" data-site="${s.name}">${__("Plan a visit")}</a>`)
					.addTo(this.layer);
				pts.push([s.gps_lat, s.gps_lng]); ns++; if (zn[s.zone_id]) zones.add(zn[s.zone_id]);
			});
		}
		if (f.show !== "sites") {
			const PC = { Critical: "#dc2626", High: "#dc2626", Medium: "#f97316", Low: "#2563eb" };
			(this.data.report_pins || []).forEach((r) => {
				if (!r.gps_lat || !r.gps_lng || !this.pass([r.area, r.road, r.site_id], r.zone_id)) return;
				if ((f.issue && r.issue_type !== f.issue) || (f.status && r.status !== f.status)) return;
				L.circleMarker([r.gps_lat, r.gps_lng], { radius: 10, color: "#111", weight: 3, fillColor: PC[r.priority] || "#f97316", fillOpacity: 0.95 })
					.bindPopup(`<b>${e(r.issue_type)}</b> · ${e(r.priority || "")}<br>${e([r.area, r.road].filter(Boolean).join(", "))}<br>${e(zn[r.zone_id] || __("Zone not set"))} · ${e(r.status)}
					${r.assigned_volunteer_name ? "<br>" + __("Volunteer") + ": " + e(r.assigned_volunteer_name) : ""}${r.photo_url ? `<br><a href="${e(r.photo_url)}" target="_blank"><img src="${e(r.photo_url)}" style="width:140px;border-radius:6px;margin-top:4px"></a>` : ""}<br>
					<a href="/app/hr-tree-report/${r.name}">${__("Open")}</a> · <a href="#" data-act="assign" data-rep="${r.name}">${__("Assign volunteer")}</a> · <a href="#" data-act="visit" data-site="${r.site_id || ""}">${__("Plan a visit")}</a>`)
					.addTo(this.layer);
				pts.push([r.gps_lat, r.gps_lng]); nr++; if (zn[r.zone_id]) zones.add(zn[r.zone_id]);
			});
		}
		$("#hrc-sum").text(`${nr} ${__("reports")} · ${ns} ${__("sites")}${zones.size ? " · " + __("Zone") + ": " + [...zones].join(", ") : ""}`);
		if (pts.length) this.map.fitBounds(pts, { padding: [30, 30], maxZoom: 17 });
		setTimeout(() => this.map.invalidateSize(), 200);
	}

	act(a, site, rep) {
		if (a === "plant") return window.open("/hasiruratha", "_blank");
		if (a === "citizen") return $("#hrc-cit")[0].scrollIntoView({ behavior: "smooth" });
		if (a === "dups") return $("#hrc-dups")[0].scrollIntoView({ behavior: "smooth" });
		if (!this.data) return frappe.show_alert(__("Still loading, try again in a moment"));
		if (a === "report") return this.reportDialog();
		if (a === "visit") return this.visitDialog(site);
		if (a === "assign") return this.assignDialog(rep);
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

	assignDialog(rep) {
		const d = new frappe.ui.Dialog({
			title: __("Assign a volunteer"),
			fields: [
				{ fieldname: "mode", fieldtype: "Select", label: __("Assign to"), options: "A tree\nA tree report", default: rep ? "A tree report" : "A tree" },
				{ fieldname: "tree_id", fieldtype: "Autocomplete", label: __("Tree"), depends_on: "eval:doc.mode=='A tree'", mandatory_depends_on: "eval:doc.mode=='A tree'",
				  options: this.opts(this.data.trees, (t) => ({ label: `${t.tree_id} · ${t.species || ""} · ${t.site_id}${t.owner_volunteer_id ? " · " + t.owner_volunteer_id : ""}`, value: t.tree_id })) },
				{ fieldname: "report_id", fieldtype: "Autocomplete", label: __("Report"), depends_on: "eval:doc.mode=='A tree report'", mandatory_depends_on: "eval:doc.mode=='A tree report'", default: rep || "",
				  options: this.opts(this.data.reports, (r) => ({ label: `${r.report_id} · ${r.tree_id} · ${r.issue_type} (${r.status})`, value: r.report_id })) },
				{ fieldname: "volunteer_id", fieldtype: "Autocomplete", label: __("Volunteer"), reqd: 1,
				  options: this.opts(this.data.volunteers, (v) => ({ label: `${v.volunteer_name} (${v.volunteer_id})${v.area ? " · " + v.area : ""}`, value: v.volunteer_id })) },
			],
			primary_action_label: __("Assign"),
			primary_action: (v) => frappe.xcall(`${HRC}.assign`, {
				tree_id: v.mode === "A tree" ? v.tree_id : null, report_id: v.mode === "A tree report" ? v.report_id : null, volunteer_id: v.volunteer_id,
			}).then(() => { d.hide(); frappe.show_alert({ message: __("Volunteer assigned"), indicator: "green" }); this.load(); }),
		});
		d.show();
	}

	review(kind, name, other) {
		if (kind === "delete") return frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", reqd: 1, label: __("Why is this a duplicate?"),
			description: __("Trees and records of this site move to {0}. A full copy is kept in HR Deleted Site.", [other]) },
			(v) => frappe.xcall(`${HR_SITE}.delete_duplicate`, { name, reason: v.reason }).then(() => { frappe.show_alert({ message: __("Deleted. A copy is in HR Deleted Site."), indicator: "green" }); this.load(); }),
			__("Delete duplicate site {0}", [name]), __("Delete"));
		const go = () => frappe.xcall(`${HR_SITE}.${kind === "merge" ? "merge_site" : "approve_site"}`, { name }).then(() => this.load());
		kind === "merge"
			? frappe.confirm(__("Move all trees, visits and reports of {0} to {1} and mark it Merged?", [name, other]), go)
			: go();
	}
}
