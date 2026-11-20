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
| become-a-volunteer | HR Volunteer Request | full_name, mobile, email, verification_code, address, road, area, pincode, zone, tree_preference, reason (all mandatory except the last two) |

## 2. Citizen side (all Frappe website pages and Web Forms)
* `/citizen-login` mobile + email (no OTP) -> `/citizen-home` dashboard (numbers, charts, zones, volunteer names only)
* `/plant-a-tree/new`, `/report-a-tree/new`, `/become-a-volunteer/new`
* `/my-status` thank-you, trees, reports with progress, volunteer application
* Share `/citizen-login` as the link or QR code. To make the site root open it: Website Settings > Home Page = `citizen-login`.

## 3. Admin side (Desk)
The workspace **Hasiru Ratha Admin** is built by hand on the site (not shipped in the app, so a migrate never overwrites it).
Number Cards you can add to it: Sites Needing Review, Volunteer Applications Pending, Citizen Plantings To Review, Citizen Reports To Review, Open Tree Reports, Trees Planted, Active Volunteers, Reports Resolved, Trees With Guard.
Admin to-do: every submission creates a ToDo for HR Admins (ToDo list or the Console).

## 4. Roles
HR Admin = everything. HR Citizen = created automatically for citizens, sees only their own submissions.

## 5. Test
Register a citizen on /citizen-login, plant twice at one spot (second should show the matching spot), send a report, apply as volunteer (code by email), approve in HR Application, check /my-status and the Console.
