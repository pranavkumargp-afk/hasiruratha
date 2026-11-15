
frappe.ready(function () {
  const wf = frappe.web_form, REPORT = true;
  let seq = 0, lock = false;
  const geo = (lat, lng) => ({ type: "FeatureCollection", features: [{ type: "Feature", properties: { point_type: "circlemarker", radius: 10 }, geometry: { type: "Point", coordinates: [lng, lat] } }] });
  function setPin(lat, lng) { lock = true; try { wf.set_value("location", JSON.stringify(geo(lat, lng))); } catch (e) {} setTimeout(() => (lock = false), 800); }
  function apply(lat, lng) {
    wf.set_value("latitude", lat); wf.set_value("longitude", lng);
    const my = ++seq;
    frappe.call({ method: "hasiruratha.citizen_api.locate", args: { lat, lng, for_report: REPORT ? 1 : 0 } }).then((r) => {
      if (my !== seq) return;
      const d = r.message || {};
      wf.set_value("area", d.area || ""); wf.set_value("road", d.road || ""); wf.set_value("address", d.address || "");
      if (REPORT) {
        const t = (d.trees || [])[0];
        wf.set_df_property("issue_type", "description", t ? "Nearest registered tree: " + (t.species || "Tree") + " (" + t.tree_id + "), " + t.distance_m + " m away." : "No registered tree within 100 m. We will record it for our team to check.");
      } else {
        const s = (d.spots || [])[0];
        wf.set_value("existing_site", s ? s.site_id : "");
        wf.set_df_property("existing_site", "description", s ? "A spot is already registered here: " + s.name + " (" + s.distance_m + " m, " + s.tree_count + " trees). Your tree will be added to it. Tick the box below if it is a different spot." : "");
      }
    });
  }
  wf.on("location", (field, value) => {
    if (lock || !value) return;
    try { const f = JSON.parse(value).features.find((x) => x.geometry.type === "Point"); if (f) apply(f.geometry.coordinates[1], f.geometry.coordinates[0]); } catch (e) {}
  });
  if (navigator.geolocation) navigator.geolocation.getCurrentPosition((p) => { setPin(p.coords.latitude, p.coords.longitude); apply(p.coords.latitude, p.coords.longitude); },
    () => { frappe.msgprint(__("We could not read your location. Please allow location access, or drop a pin on the map.")); }, { enableHighAccuracy: true, timeout: 12000 });
});
