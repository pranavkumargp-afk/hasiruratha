# Hasiruratha: Frappe-native setup guide

## 1. Deploy
1. Push the repo, update the app on Frappe Cloud, run **Migrate** (creates the HR Citizen role, 3 new DocTypes, 3 Web Forms, new fields).
2. Search **Email Account** -> add an outgoing account (needed for the volunteer verification code).
3. Search **Web Form** -> check `plant-a-tree`, `report-a-tree`, `become-a-volunteer` exist and are **Published**.
   If any is missing or its script does not run, create it by hand (Web Form > New): pick the DocType, tick *Login Required*, *Allow Multiple*, *Show List*, add the fields below, and paste the script from `hasiruratha/web_form/<name>/<name>.js` into **Client Script**.

| Web Form | DocType | Fields to show |
|---|---|---|
| plant-a-tree | HR Citizen Planting | photo, tree_type, location, area, road, latitude, longitude, address, existing_site, different_spot, willing_to_volunteer |
| report-a-tree | HR Citizen Report | photo, issue_type, location, area, road, latitude, longitude, address, notes |
| become-a-volunteer | HR Volunteer Request | email, verification_code, area, tree_preference, reason |

## 2. Citizen side (all Frappe website pages and Web Forms)
* `/citizen-login` mobile + email (no OTP) -> `/citizen-home` dashboard (numbers, charts, zones, volunteer names only)
* `/plant-a-tree/new`, `/report-a-tree/new`, `/become-a-volunteer/new`
* `/my-status` thank-you, trees, reports with progress, volunteer application
* Share `/citizen-login` as the link or QR code. To make the site root open it: Website Settings > Home Page = `citizen-login`.

## 3. Admin side (Desk)
Workspace "Hasiru Ratha Admin" > Edit > add Shortcuts:
| Label | Type | Link |
|---|---|---|
| Console | Page | hr-console |
| Citizen Plantings | DocType | HR Citizen Planting (List) |
| Citizen Reports | DocType | HR Citizen Report (List) |
| Report Map | URL | /app/hr-citizen-report/view/map |
| Planting Map | URL | /app/hr-citizen-planting/view/map |
| Volunteer Requests | DocType | HR Volunteer Request (List) |
| Review Duplicates | DocType | HR Site, filter Status = Needs Review |
Add Number Cards: Sites Needing Review, Citizen Plantings To Review, Citizen Reports To Review, Volunteer Applications Pending.
In each list use the filter bar: Zone, Area (type e.g. "Electronic City"), Status, Issue type. Change **Zone** on a submission to correct it; the site and report follow.
Admin to-do: every submission creates a ToDo for HR Admins (ToDo list or the Console).

## 4. Roles
HR Admin = everything. HR Citizen = created automatically for citizens, sees only their own submissions.

## 5. Test
Register a citizen on /citizen-login, plant twice at one spot (second should show the matching spot), send a report, apply as volunteer (code by email), approve in HR Application, check /my-status and the Console.
