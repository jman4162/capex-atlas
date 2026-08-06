"""Economic asset classes.

These cut across how filers group property and equipment, because the economics
that matter here (how long an asset takes to install, how long it lasts) do not
line up with the categories a balance sheet uses.
"""

from __future__ import annotations

from enum import StrEnum


class CapitalCategory(StrEnum):
    LAND = "land"
    BUILDINGS = "buildings"
    POWER = "power"
    COOLING = "cooling"
    SERVERS = "servers"
    ACCELERATORS = "accelerators"
    NETWORKING = "networking"
    STORAGE = "storage"
    CAPITALIZED_SOFTWARE = "capitalized_software"
    FINANCE_LEASES = "finance_leases"
    CONSTRUCTION_IN_PROGRESS = "construction_in_progress"
    UNALLOCATED = "unallocated"
    """The honest bucket. Most reported capex never gets broken out further."""
