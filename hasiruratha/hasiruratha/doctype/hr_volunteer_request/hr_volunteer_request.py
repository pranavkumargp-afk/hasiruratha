import frappe
from frappe.model.document import Document

from hasiruratha import citizen_forms as cf


class HRVolunteerRequest(Document):
	def validate(self):
		if self.is_new():
			cf.before_volunteer(self)

	def after_insert(self):
		cf.after_volunteer(self)
