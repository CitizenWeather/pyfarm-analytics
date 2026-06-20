"""Public convenience API for pyfarm-analytics.

These module-level functions instantiate an ``Analyzer`` with the default
storage backend (obtained from ``pyfarm.storage.get_backend``) and delegate
to the appropriate method.

They are the recommended entry-point for callers that do not need to manage
the storage backend lifetime themselves (e.g. one-off jobs in pyfarm-scheduler
or route handlers in pyfarm-api).

Example::

    from pyfarm.analytics.queries import get_dashboard

    dashboard = await get_dashboard(grow_id="g-001", start=start_dt, end=end_dt)
"""

from __future__ import annotations

from datetime import datetime

from pyfarm.core.storage import get_backend

from pyfarm.analytics.analyzer import Analyzer
from pyfarm.analytics.models import (
    AnomalyRecord,
    EnvironmentSummary,
    KPIDashboard,
    NutrientDriftRecord,
)


def _get_analyzer() -> Analyzer:
    """Return an Analyzer backed by the default storage backend."""
    return Analyzer(get_backend())


async def get_environment_summary(
    grow_id: str,
    start: datetime,
    end: datetime,
    stage: str = "unknown",
) -> EnvironmentSummary:
    """Compute and return an environment summary for *grow_id*.

    Args:
        grow_id: Grow session identifier.
        start:   Period start (UTC-aware datetime).
        end:     Period end (UTC-aware datetime).
        stage:   Optional growth stage label.

    Returns:
        EnvironmentSummary with averaged temperature, RH, VPD, CO2, DLI.
    """
    return await _get_analyzer().environment_summary(grow_id, start, end, stage=stage)


async def get_nutrient_drift(
    grow_id: str,
    start: datetime,
    end: datetime,
) -> list[NutrientDriftRecord]:
    """Compute and return nutrient drift records for *grow_id*.

    Args:
        grow_id: Grow session identifier.
        start:   Period start.
        end:     Period end.

    Returns:
        List of NutrientDriftRecord.
    """
    return await _get_analyzer().nutrient_drift(grow_id, start, end)


async def get_anomalies(
    grow_id: str,
    sensor_id: str,
    start: datetime,
    end: datetime,
    threshold: float = 3.0,
) -> list[AnomalyRecord]:
    """Detect and return anomalous readings for *sensor_id* in *grow_id*.

    Args:
        grow_id:   Grow session identifier.
        sensor_id: Sensor to analyse.
        start:     Period start.
        end:       Period end.
        threshold: Z-score threshold (default 3.0).

    Returns:
        List of AnomalyRecord.
    """
    return await _get_analyzer().anomalies(
        grow_id, sensor_id, start, end, threshold=threshold
    )


async def get_dashboard(
    grow_id: str,
    start: datetime,
    end: datetime,
) -> KPIDashboard:
    """Build and return a full KPI dashboard for *grow_id*.

    Args:
        grow_id: Grow session identifier.
        start:   Period start.
        end:     Period end.

    Returns:
        KPIDashboard aggregating all computed KPIs.
    """
    return await _get_analyzer().dashboard(grow_id, start, end)
