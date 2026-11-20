# Copyright (c) 2026, Hasiru Ratha and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HRApplication(Document):
	def validate(self):
		# A volunteer may apply without choosing a tree; an admin assignment always needs one.
		if self.application_type == "Admin Assignment" and not self.tree:
			frappe.throw(_("Tree is mandatory for an Admin Assignment"))
