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

## CHANGELOG
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
