import frappe
from frappe.model.document import Document

from hasiruratha import citizen_forms as cf


class HRCitizenPlanting(Document):
	def validate(self):
		if self.is_new():
			cf.before_plant(self)

	def after_insert(self):
		cf.after_plant(self)

	def on_update(self):
		cf.zone_changed(self, "site")
