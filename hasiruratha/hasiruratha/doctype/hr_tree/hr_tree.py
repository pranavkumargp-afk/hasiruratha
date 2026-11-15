from frappe.model.document import Document
from frappe.utils import flt


class HRTree(Document):
	def validate(self):
		if flt(self.gps_lat) and flt(self.gps_lng):
			self.latitude, self.longitude = flt(self.gps_lat), flt(self.gps_lng)
