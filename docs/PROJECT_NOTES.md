# Hasiruratha: discussion notes and status

## Review points (11 Nov 2026)
| # | Point | Status |
|---|-------|--------|
| 1 | Walkthrough of the HR app built on the local bench | Done |
| 2 | Duplicate site detection / review / verify for user and admin | Built, needs test on Frappe Cloud (see below) |
| 3 | App did not follow Frappe UI/UX | Admin side uses Desk (workspace, list, form, number cards, ToDo). User app (`/hasiruratha`) is still a custom SPA: re-skin is a later phase |
| 4 | New bench/site on Frappe Cloud, redo doctypes | Site `hasiruratha.nvi.frappe.cloud` created, data restored |
| 5 | "Submit report" wording unsuitable for citizens | Reworded on the user screens (see CHANGELOG below) |
| 6 | Use common Frappe UI components | Number Cards, list indicators, form buttons, ToDo assignment, workspace shortcuts |
| 7 | Mobile compliant | SPA is responsive; the new "spots near you" panel is built for phones |

## Duplicate-site mechanism
Server (`hr_site.py`, runs on every new HR Site):
* a new site is flagged **Needs Review** (not blocked) when another non-merged site of the same type is within **25 m**, or is on the **same road + area within 150 m**
* "same road + area" alone is NOT used: `add_site` sets area = road, so it would flag every site on a long road
* `Possible Duplicate Of` is filled, and every HR Admin gets a ToDo

Admin (Desk):
* open the flagged HR Site: orange banner + **Review** menu: *Different site - keep it* / *Same place - merge*
* merge moves trees, visits, conditions and tree reports to the existing site, recounts trees, marks the duplicate **Merged**
* Number Cards: *Sites Needing Review*, *Volunteer Applications Pending*, *Open Tree Reports*

Citizen (Quick Add, `/hasiruratha`):
* after GPS is captured the app shows **spots near you** (300 m) as a radar plot + cards, closest first
* tap **This is my spot** to add the tree to the existing spot, or **No, this is a different spot** to create a new one
* within 30 m the user must choose one of the two before saving
* if the server still finds a near match, the user sees a thank-you message and the admin confirms

## Admin Console (Desk page `hr-console`)
Open `/app/hr-console`. Tiles: Plant a sapling (opens `/hasiruratha`), Report a tree, Plan a visit, Assign a volunteer (to a tree or a report), Review duplicates. Below: live OpenStreetMap map of all sites (orange = Needs Review, popup has Open / Plan a visit) and the duplicate queue with Different site / Merge buttons. Add a Shortcut to it in the workspace (Type = Page, Link To = hr-console).

## Planting flows
* **Quick Add (live GPS):** GPS -> spots near you (radar + cards) -> reuse a spot or create new
* **Manual Add (pin on map):** after the pin is set and Save is tapped, if a spot is within 30 m the user must choose *Use this spot* or *No, this is a different spot*
* both flows: the server still flags Needs Review if a near match slips through

## Citizen portal (`/citizen`)
* **Login:** mobile number + email, no OTP. First time also asks for a name. Creates a user with only the `HR Citizen` role. An existing email must come with the same mobile number. Admin accounts can never sign in here.
* **Dashboard:** totals (trees, zones, sites, volunteers), trees per month, trees by status, browse zones -> sites -> trees, volunteer NAMES only (phone/email are never sent to the browser).
* **Plant a tree:** photo (required) -> location from the photo, else phone GPS, else a map pin -> area/road/zone auto-filled and editable -> tree type -> "willing to volunteer?" -> save. If a spot is within 30 m the citizen is asked to reuse it.
* **Report a tree:** photo (required) -> location -> pick the nearest registered tree (or "not listed") -> issue -> send. A tree that is not in the records is saved as a flagged, unconfirmed entry for admin to verify.
* **Volunteer:** email verification code, then an HR Application (Pending, email verified) and a ToDo for HR Admins. Approve / Reject buttons on the HR Application form. Several volunteers can apply for the same tree; the first approved one becomes the tree's owner volunteer.
* **My status:** the citizen's own trees, reports (with assigned volunteer name) and volunteer application.
* **Admin side:** Console tile + panel "Citizen submissions" (photo, address, zone guess and why, who, when; confirm or change the zone; plan a visit; open site). ToDos for every submission. Number Cards: Citizen Plantings To Review, Citizen Reports To Review.
* **Needs setup:** an outgoing Email Account on the site (for the verification code); the HR Citizen role is created on migrate.

## Admin: area search, map and filters
* Console map filter bar: search area/road (e.g. "Electronic City"), zone, sites/reports, issue type, status. The summary line lists the zones the matches fall in. Report pins are coloured by priority; popups have Open / Assign volunteer / Plan a visit. Citizen submissions are filtered the same way.
* HR Site, HR Tree, HR Tree Report have `latitude` / `longitude` (copied from GPS), so Frappe's own **Map** view works: `/app/hr-tree-report/view/map`, `/app/hr-site/view/map`.
* Standard filters: HR Tree Report (zone, site, area, issue type, status, priority, submitted via, admin reviewed), HR Site (area, road, zone, status).
* Citizen "My status": thank-you note, tree messages, report progress bar (Received, Seen, Volunteer, In progress, Resolved).

## Frappe-native citizen side (replaces the custom `/citizen` page)
Citizens use Frappe Web Forms and website pages. Each submission is first saved as a record the admin can filter and map (HR Citizen Planting, HR Citizen Report, HR Volunteer Request), then processed into the real site / tree / report / volunteer application by `citizen_forms.py`. Status flows back to the citizen automatically. The earlier custom page (`templates/citizen.html`, route `/citizen`) is still in the repo and can be deleted. See `docs/FRAPPE_SETUP.md`.

## CHANGELOG
* `citizen_api.py`, `templates/citizen.html`, `renderer.py` route `/citizen`; new fields `submitted_via`, `address_full`, `zone_note`, `admin_reviewed` (HR Site / Tree / Tree Report), `email_verified` (HR Application)
* `page/hr_console/*`: the Console page; python endpoints reuse `api.add_visit`, `create_tree_report`, `assign_tree`, `assign_tree_report`
* `hr_site.py`: duplicate detection, approve and merge
* `hr_site.json`: field `possible_duplicate_of`, status `Needs Review`
* `hr_site.js`, `hr_site_list.js`: admin review buttons, status colours
* `api.py`: actions `getNearbySites`, `approveSite`, `mergeSite`; `addSite` returns `needs_review`
* `number_card/*`: three admin cards
* `templates/app.html`: nearby-spots panel; wording: "Save plantation to Tree Registry" -> "Save my planted tree", "Report condition" -> "How is this tree doing?", "Submit report" -> "Send update" / "Send to the Hasiru Ratha team", "Report a Tree" -> "Help a tree", "Report a tree issue" -> "Tell us what this tree needs"

## Open items
* test on the cloud site: create two sites 10 m apart, confirm Needs Review, ToDo, approve, merge
* decide whether to rebuild the user app with Frappe UI (Vue) later
