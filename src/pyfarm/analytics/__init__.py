"""pyfarm-analytics: KPI computation library for the pyfarm ecosystem.

Provides environmental summaries, nutrient drift tracking, anomaly detection,
and yield analytics consumed by pyfarm-scheduler (background jobs) and
pyfarm-api (dashboard routes).

Quick start::

    from pyfarm.analytics import Analyzer
    from pyfarm.storage import get_backend

    storage = get_backend()
    analyzer = Analyzer(storage)

    summary = await analyzer.environment_summary(grow_id, start, end)
    drifts  = await analyzer.nutrient_drift(grow_id, start, end)
    anomalies = await analyzer.anomalies(grow_id, "env", start, end)
    dashboard = await analyzer.dashboard(grow_id, start, end)

Or use the one-liner query helpers::

    from pyfarm.analytics.queries import get_dashboard
    dashboard = await get_dashboard(grow_id, start, end)
"""

from pyfarm.analytics.analyzer import Analyzer
from pyfarm.analytics.models import (
    AnomalyRecord,
    EnvironmentSummary,
    KPIDashboard,
    NutrientDriftRecord,
    YieldRecord,
)
from pyfarm.analytics.queries import (
    get_anomalies,
    get_dashboard,
    get_environment_summary,
    get_nutrient_drift,
)

__version__ = "0.1.0"

__all__ = [
    # Core class
    "Analyzer",
    # Models
    "YieldRecord",
    "EnvironmentSummary",
    "NutrientDriftRecord",
    "AnomalyRecord",
    "KPIDashboard",
    # Query helpers
    "get_environment_summary",
    "get_nutrient_drift",
    "get_anomalies",
    "get_dashboard",
]
