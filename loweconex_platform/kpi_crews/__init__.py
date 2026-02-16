"""
KPI Crews — multi-agent teams for each ROI driver.

Each KPI crew follows the mandatory structure:
  Research Agent → Extraction Agent → Calculation Agent → QA Agent

14 KPI crews are instantiated from the base template.
"""

from loweconex_platform.kpi_crews.base_crew import KPICrewFactory, KPICrewResult
from loweconex_platform.kpi_crews.tools import LoweconexTools
from loweconex_platform.kpi_crews.registry import KPI_REGISTRY, get_all_kpi_names

__all__ = [
    "KPICrewFactory",
    "KPICrewResult",
    "LoweconexTools",
    "KPI_REGISTRY",
    "get_all_kpi_names",
]
