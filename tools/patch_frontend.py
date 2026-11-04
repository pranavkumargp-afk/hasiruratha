# Re-creates templates/app.html from the original index.html (edit the two paths below). Keeps the UI identical and swaps only API/login/photo/geocode.
import re, sys
src = open('/mnt/user-data/uploads/index.html', encoding='utf-8').read().replace('\r\n', '\n')

def sub_once(pattern, repl, s, flags=re.S, label=''):
    n = len(re.findall(pattern, s, flags))
    if n != 1:
        sys.exit(f'PATCH FAILED ({label or pattern[:50]}): matched {n} times')
    return re.sub(pattern, lambda m: repl, s, count=1, flags=flags)

def rep_once(old, new, s, label=''):
    n = s.count(old)
    if n != 1:
        sys.exit(f'PATCH FAILED ({label or old[:50]}): found {n} times')
    return s.replace(old, new)

s = src

# 0. boot data, injected by the Frappe renderer, must exist before the app script runs
s = rep_once('<script>\n// ═══════════════════════════════════════════════════════════════════\n//  CONFIG',
 '<script>window.HR_BOOT = __HR_BOOT__;</script>\n<script>\n// ═══════════════════════════════════════════════════════════════════\n//  CONFIG', s, 'boot')

# 1. config: no Apps Script URL, no client-side admin PIN
s = sub_once(r"const SCRIPT_URL  = '[^']*';\n", "const HR_BOOT_DATA = window.HR_BOOT || { logged_in: false };\nconst CSRF_TOKEN   = HR_BOOT_DATA.csrf_token || '';\n", s, label='script url')
s = rep_once("const ADMIN_PIN   = '2026';\n", "", s, 'admin pin')

# 2. session = the Frappe session (server is the source of truth, not localStorage)
s = sub_once(r"function saveSession\(u\).*?function clearSession\(\)[^\n]*\n",
"""function saveSession(u) { /* session lives in the Frappe cookie */ }
function loadSession() { return HR_BOOT_DATA.logged_in ? HR_BOOT_DATA.user : null; }
function clearSession() { /* handled by /api/method/logout */ }
""", s, label='session fns')

# 3. api(): JSONP -> Frappe whitelisted method
s = sub_once(r"function api\(action, data = \{\}\) \{.*?\n\}\n(?=\n// ═+\n//  PHOTO UTILITIES)",
"""async function frappePost(method, params = {}) {
  const body = new URLSearchParams();
  Object.keys(params).forEach(k => {
    const v = params[k];
    if (v !== undefined && v !== null) body.append(k, typeof v === 'string' ? v : JSON.stringify(v));
  });
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 25000);
  try {
    const res = await fetch('/api/method/' + method, {
      method: 'POST', credentials: 'same-origin', signal: ctl.signal,
      headers: { 'X-Frappe-CSRF-Token': CSRF_TOKEN, 'Accept': 'application/json' },
      body,
    });
    if (res.status === 401 || res.status === 403) {
      if (HR_BOOT_DATA.logged_in) { showToast('Session expired — signing in again'); setTimeout(() => location.reload(), 900); }
      return { success: false, error: 'Please sign in again' };
    }
    if (res.status === 429) return { success: false, error: 'Too many attempts. Please wait a few minutes.' };
    const json = await res.json().catch(() => null);
    if (!json) return { success: false, error: 'Server error (' + res.status + ')' };
    if (json.message !== undefined && !json.exc) return json.message;
    return { success: false, error: (json._error_message || json.exception || 'Server error').toString().replace(/<[^>]+>/g, '') };
  } catch (e) {
    return { success: false, error: e.name === 'AbortError' ? 'Timeout' : 'Network error' };
  } finally { clearTimeout(t); }
}

function api(action, data = {}) {
  const clean = {};
  Object.keys(data).forEach(k => { if (data[k] !== undefined) clean[k] = data[k]; });
  return frappePost('hasiruratha.api.call', { action, data: JSON.stringify(clean) });
}
""", s, label='api()')

# 4. photos -> Frappe File (was Cloudflare worker -> Google Drive)
s = sub_once(r"async function uploadToDrive\(base64, entityId, entityType, zoneId\) \{.*?\n\}\n",
"""async function uploadToDrive(base64, entityId, entityType, zoneId) {
  const zoneName = ZONE_NAMES[zoneId] || 'General';
  const date     = new Date().toISOString().slice(0, 10);
  const filename = entityId + '_' + entityType + '_' + date + '.jpg';
  showToast('Uploading photo...');
  const r = await frappePost('hasiruratha.api.upload_photo', { base64_data: base64, filename, zone_name: zoneName });
  if (r && r.success) { showToast('Photo saved'); return r.url; }
  showToast('Photo upload failed: ' + ((r && r.error) || 'unknown'));
  return null;
}
""", s, label='uploadToDrive')
s = rep_once("KB — tap Save to upload to Drive", "KB — tap Save to upload", s, 'photo hint')

# 5. login: mobile number -> Frappe session; admin -> Frappe login page
s = rep_once("document.getElementById('pin-field').style.display = chk.checked ? '' : 'none';",
             "document.getElementById('pin-field').style.display = 'none';  // admins use the secure Frappe login", s, 'toggle admin')
s = rep_once("""  if (!phone)                         { showErr('login-err','Please enter your mobile number.'); return; }
  if (isAdmin && pin !== ADMIN_PIN)   { showErr('login-err','Incorrect admin PIN.'); return; }
""", """  if (isAdmin) { window.location.href = '/login?redirect-to=%2Fhasiruratha'; return; }
  if (!phone)  { showErr('login-err','Please enter your mobile number.'); return; }
""", s, 'doLogin checks')
s = rep_once("const res = await api('checkVolunteer', { phone });", "const res = await frappePost('hasiruratha.api.login_phone', { phone });", s, 'checkVolunteer')
s = rep_once("""    showErr('login-err', 'Could not connect. Check internet or try incognito window.');""",
             """    showErr('login-err', res.error && res.error !== 'Network error' ? res.error : 'Could not connect. Check your internet and try again.');""", s, 'login err')
s = rep_once("  enterApp({ ...res.volunteer, role: isAdmin ? 'admin' : 'volunteer' }, isAdmin);\n}",
             "  window.location.reload();   // the server session cookie is set; reload boots the app signed-in\n}", s, 'login enter')
s = rep_once("const res = await api('registerVolunteer', { name, phone, email, area, group_id: GROUP_ID });",
             "const res = await frappePost('hasiruratha.api.register_phone', { name, phone, email, area, group_id: GROUP_ID });", s, 'register')
s = rep_once("  enterApp({ ...res.volunteer, role: 'volunteer' }, false);\n}",
             "  setTimeout(() => window.location.reload(), 700);\n}", s, 'register enter')

# 6. logout
s = sub_once(r"function doLogout\(\) \{.*?\n\}\n(?=\nfunction showErr)",
"""function doLogout() {
  clearCache();
  fetch('/api/method/logout', { method: 'POST', credentials: 'same-origin', headers: { 'X-Frappe-CSRF-Token': CSRF_TOKEN } })
    .finally(() => { window.location.href = '/hasiruratha'; });
}
""", s, label='doLogout')

# 7. geolocation: browser reads the GPS, SERVER does the reverse-geocode
s = sub_once(r"async function reverseGeocode\(lat, lng\) \{.*?\n\}\n(?=\n// ─── Photo handler)",
"""async function reverseGeocode(lat, lng) {
  const roadEl    = document.getElementById('qa-road-txt');
  const roadInput = document.getElementById('qa-road');
  try {
    const r = await api('reverseGeocode', { lat, lng });
    const suggested = r.success ? (r.road || r.area || '') : '';
    if (suggested) {
      roadEl.innerHTML = '📍 Suggested: <strong>' + suggested.replace(/</g, '&lt;') + '</strong>';
      if (!roadInput.value) roadInput.value = suggested;
    } else {
      roadEl.textContent = r.success ? 'Could not identify road — enter manually' : 'Enter road name manually';
    }
  } catch (e) {
    roadEl.textContent = 'Geocode failed — enter road manually';
  }
}
""", s, label='reverseGeocode')
s = sub_once(r"async function reverseGeocodeBackground\(lat,lng,txtId,inputId\)\{.*?\n\}\n(?=\nasync function submitQuickAdd)",
"""async function reverseGeocodeBackground(lat,lng,txtId,inputId){
  try{
    const r = await api('reverseGeocode',{lat,lng});
    if(!r.success) return;
    const suggested = r.road || r.area || '';
    if(txtId&&suggested){const el=document.getElementById(txtId);if(el)el.textContent='Road: '+suggested;}
    if(inputId){const el=document.getElementById(inputId);if(el&&!el.value)el.value=suggested;}
    // Also update the site road silently if we have a site_id pending
    if(window._qaSiteId&&suggested) api('updateSite',{site_id:window._qaSiteId,road:suggested,area:suggested});
  }catch(e){}
}
""", s, label='reverseGeocodeBackground')

# 8. maps key comes from Hasiruratha Settings, not from the repo
s = sub_once(r"key=AIza[0-9A-Za-z_\-]+&callback=onMapsReady", "key=__GMAPS_KEY__&callback=onMapsReady", s, label='maps key')

# 9. contact masking now happens on the server; don't double-mask
s = rep_once("function maskPhone(phone) {\n", "function maskPhone(phone) {\n  if (String(phone || '').includes('•')) return phone;   // already masked by the server\n", s, 'maskPhone')
s = rep_once("function maskEmail(email) {\n", "function maskEmail(email) {\n  if (String(email || '').includes('•')) return email;   // already masked by the server\n", s, 'maskEmail')

# 10. login label
s = rep_once("<span>Admin login</span>", "<span>Admin login (opens the secure sign-in page)</span>", s, 'admin label')


# 11. boot path: use enterApp() so admin-only UI (Sites tab, manual add, merged chip) shows after the login reload
s = sub_once(r"const sess = loadSession\(\);\nif \(sess\) \{.*?\n\}\n</script>",
"const sess = loadSession();\nif (sess) { enterApp(sess, sess.role === 'admin'); }\n</script>", s, label='init block')

# sanity: nothing from the old stack should survive
for bad in ('script.google.com', 'workers.dev', 'ADMIN_PIN', 'SCRIPT_URL', 'AIza'):
    if bad in s: sys.exit('LEFTOVER: ' + bad)

out = '/home/claude/hasiruratha/hasiruratha/templates/app.html'
open(out, 'w', encoding='utf-8').write(s)
print('patched OK ->', out, len(s), 'bytes')
