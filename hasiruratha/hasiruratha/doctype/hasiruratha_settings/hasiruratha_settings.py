from frappe.model.document import Document

from hasiruratha import citizen_api as ca


class HasirurathaSettings(Document):
	def validate(self):
		for row in self.get("gallery") or []:
			row.image = ca.make_public(row.image)
