frappe.ready(function () {
  const wf = frappe.web_form;
  const MODE = "plant"; // "plant" | "report" | "volunteer"
  const REPORT = MODE === "report";
  const SHOW_NEARBY = MODE === "plant";

  let seq = 0;        // only the latest locate() result is used
  let lock = false;   // ignore change events caused by our own set_value
  let group = null;   // layer for nearby (orange) spots
  let me = null;      // the user's (blue) location marker

  const esc = (t) =>
    String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  // Safe helpers: skip fields that do not exist on this web form
  const has = (f) => wf.fields_dict && wf.fields_dict[f];
  const setVal = (f, v) => (has(f) ? wf.set_value(f, v) : null);
  const setDesc = (f, d) => { if (has(f)) wf.set_df_property(f, "description", d); };

  const getMap = () => has("location") && wf.fields_dict.location.map;

  // ---------- Map drawing ----------

  const dot = (color, size, border) =>
    L.divIcon({
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      html:
        "<div style='width:" + size + "px;height:" + size + "px;border-radius:50%;background:" + color +
        ";border:" + border + "px solid #fff;box-shadow:0 0 0 2px rgba(0,0,0,.25),0 2px 6px rgba(0,0,0,.4)'></div>",
    });

  // Blue dot showing where the tree / user is (HTML marker, always visible)
  function showMe(lat, lng, zoom) {
    const map = getMap();
    if (!map || !window.L) {
      console.warn("Map not ready yet");
      return;
    }
    if (me) me.remove();
    me = L.marker([lat, lng], { icon: dot("#2563eb", 22, 3), zIndexOffset: 1000, interactive: false })
      .addTo(map)
      .bindTooltip(__("Tree location"));
    map.invalidateSize();
    if (zoom) map.setView([lat, lng], 17);
    // the map container can finish sizing late; re-center once more
    setTimeout(() => {
      map.invalidateSize();
      if (zoom) map.setView([lat, lng], 17);
    }, 400);
  }

  // Orange dots for spots already registered nearby
  function drawNearby(list) {
    const map = getMap();
    if (!map || !window.L) return;
    if (group) group.remove();
    group = L.layerGroup().addTo(map);
    (list || []).forEach((s) =>
      L.marker([s.gps_lat, s.gps_lng], { icon: dot("#f97316", 18, 2), bubblingMouseEvents: false })
        .addTo(group)
        .bindPopup(
          "<b>" + esc(s.name) + "</b><br>" +
          esc(s.distance_m) + " m away · " + esc(s.tree_count) + " trees<br>" +
          "<a href='#' class='hr-use' data-s='" + esc(s.site_id) + "'>Use this spot</a>"
        )
    );
  }

  // "Use this spot" link inside an orange popup
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest(".hr-use");
    if (!a) return;
    e.preventDefault();
    setVal("existing_site", a.dataset.s);
    setVal("different_spot", 0);
  });

  // ---------- Saving the location ----------

  const geo = (lat, lng) => ({
    type: "FeatureCollection",
    features: [{
      type: "Feature",
      properties: { point_type: "circlemarker", radius: 10 },
      geometry: { type: "Point", coordinates: [lng, lat] }, // GeoJSON is [lng, lat]
    }],
  });

  function setPin(lat, lng, zoom = true) {
    showMe(lat, lng, zoom); // what the user sees
    lock = true;
    Promise.resolve()
      .then(() => setVal("location", JSON.stringify(geo(lat, lng)))) // what gets saved
      .catch((e) => console.error("setPin failed:", e))
      .finally(() => setTimeout(() => (lock = false), 800));
  }

  // ---------- Filling the form from coordinates ----------

  function apply(lat, lng) {
    setVal("latitude", lat);
    setVal("longitude", lng);

    const my = ++seq;
    frappe
      .call({
        method: "hasiruratha.citizen_api.locate",
        args: { lat, lng, for_report: REPORT ? 1 : 0 },
      })
      .then((r) => {
        if (my !== seq) return; // a newer lookup has started
        const d = r.message || {};

        setVal("area", d.area || "");
        setVal("road", d.road || "");
        setVal("address", d.address || "");

        if (REPORT) {
          const t = (d.trees || [])[0];
          setDesc(
            "issue_type",
            t
              ? "Nearest registered tree: " + (t.species || "Tree") + " (" + t.tree_id + "), " + t.distance_m + " m away."
              : "No registered tree within 100 m. We will record it for our team to check."
          );
        } else if (SHOW_NEARBY) {
          drawNearby(d.nearby);
          const s = (d.spots || [])[0];
          setVal("existing_site", s ? s.site_id : "");
          setDesc(
            "existing_site",
            s
              ? "A spot is already registered here: " + s.name + " (" + s.distance_m + " m, " + s.tree_count +
                " trees). Your tree will be added to it. Tick the box below if it is a different spot."
              : ""
          );
        }
      })
      .catch((e) => console.error("locate failed:", e));
  }

  // ---------- User interactions ----------

  // User drops or edits a marker with the map's own toolbar
  wf.on("location", (field, value) => {
    if (lock || !value) return;
    try {
      const f = JSON.parse(value).features.find((x) => x.geometry.type === "Point");
      if (f) {
        const lat = f.geometry.coordinates[1];
        const lng = f.geometry.coordinates[0];
        showMe(lat, lng, false);
        apply(lat, lng);
      }
    } catch (e) {
      console.error("Could not read location value:", e);
    }
  });

  // User taps anywhere on the map to move the pin
  (function bindMapClick() {
    const map = getMap();
    if (!map || !window.L) return setTimeout(bindMapClick, 300); // wait until the map exists
    map.on("click", (e) => {
      setPin(e.latlng.lat, e.latlng.lng, false);
      apply(e.latlng.lat, e.latlng.lng);
    });
    addLocateButton(map);
  })();

  // ---------- Getting the user's GPS position ----------

  function onPosition(p) {
    setPin(p.coords.latitude, p.coords.longitude, true);
    apply(p.coords.latitude, p.coords.longitude);
  }

  function getPosition(manual) {
    if (!navigator.geolocation) {
      frappe.msgprint(__("Your browser cannot share location. Please tap the map to drop a pin."));
      return;
    }
    if (window.isSecureContext === false) {
      frappe.msgprint(__("Location needs a secure (https) page. Please tap the map to drop a pin."));
      return;
    }
    // 1st try: precise GPS. 2nd try: fast network/Wi-Fi location (works on laptops).
    navigator.geolocation.getCurrentPosition(
      onPosition,
      () => {
        navigator.geolocation.getCurrentPosition(
          onPosition,
          (err) => {
            console.warn("Geolocation failed:", err && err.code, err && err.message);
            frappe.msgprint(
              __("We could not read your location. Please allow location access in your browser, or tap the map to drop a pin.")
            );
          },
          { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  // "My location" button on the map so users can retry with one tap
  function addLocateButton(map) {
    const Ctl = L.Control.extend({
      options: { position: "topleft" },
      onAdd: function () {
        const b = L.DomUtil.create("a", "leaflet-bar");
        b.href = "#";
        b.title = __("Use my current location");
        b.innerHTML = "&#9678;";
        b.style.cssText =
          "background:#fff;width:30px;height:30px;line-height:30px;text-align:center;font-size:20px;color:#2563eb;display:block;text-decoration:none";
        L.DomEvent.disableClickPropagation(b);
        L.DomEvent.on(b, "click", (e) => { L.DomEvent.preventDefault(e); getPosition(true); });
        return b;
      },
    });
    new Ctl().addTo(map);
  }

  // ---------- Initial location ----------

  function startLocation() {
    if (!getMap() || !window.L) return setTimeout(startLocation, 300); // make sure the map is ready first
    getPosition(false);
  }
  startLocation();
});
