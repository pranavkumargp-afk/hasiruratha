import frappe
from frappe.model.document import Document

from hasiruratha import citizen_forms as cf


class HRCitizenReport(Document):
	def validate(self):
		if self.is_new():
			cf.before_report(self)

	def after_insert(self):
		cf.after_report(self)

	def on_update(self):
		cf.zone_changed(self, "report")
