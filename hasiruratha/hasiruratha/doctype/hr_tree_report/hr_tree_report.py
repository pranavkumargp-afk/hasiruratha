import frappe
from frappe.model.document import Document
from frappe.utils import flt


class HRTreeReport(Document):
	def validate(self):
		site = frappe.db.get_value("HR Site", self.site_id, ["area", "road", "gps_lat", "gps_lng"], as_dict=True) if self.site_id else None
		if site:
			self.area = self.area or site.area
			self.road = self.road or site.road
			if not (flt(self.gps_lat) and flt(self.gps_lng)):
				self.gps_lat, self.gps_lng = site.gps_lat, site.gps_lng
		if flt(self.gps_lat) and flt(self.gps_lng):
			self.latitude, self.longitude = flt(self.gps_lat), flt(self.gps_lng)
