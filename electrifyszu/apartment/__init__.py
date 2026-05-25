"""Apartment (丽湖) power API — 172.25.100.105:8010 ASP.NET system."""

from electrifyszu.apartment.api import ApartmentPowerApi  # noqa: F401
from electrifyszu.apartment.buildings import Building, get_building, load_buildings, normalize_building_code  # noqa: F401
