"""Nutrient drift computation for pyfarm-analytics."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from pyfarm.analytics.models import NutrientDriftRecord

if TYPE_CHECKING:
    from pyfarm.core.storage import StorageBackend

# Metric identifiers as stored in sensor readings
_METRIC_PH = "ph"
_METRIC_EC = "ec"

# Drift-rate thresholds that trigger the `flagged` field
_THRESHOLD_PH = 0.1   # pH units / day
_THRESHOLD_EC = 0.2   # mS/cm / day

# Sensor id used when querying storage for nutrient readings
_SENSOR_NUTRIENT = "nutrient"


class NutrientAnalyzer:
    """Computes nutrient drift KPIs from EC and pH readings."""

    async def compute_drift(
        self,
        storage: "StorageBackend",
        grow_id: str,
        start: datetime,
        end: datetime,
    ) -> list[NutrientDriftRecord]:
        """Calculate EC and pH drift over the requested period.

        Queries the storage backend for nutrient sensor readings, separates
        pH and EC values, fits a linear regression to each series, and
        derives a drift_rate (units/day).  Records whose |drift_rate| exceeds
        the per-metric threshold are flagged.

        Args:
            storage:  Async StorageBackend instance.
            grow_id:  Grow session identifier.
            start:    Period start (UTC-aware datetime).
            end:      Period end (UTC-aware datetime).

        Returns:
            List of NutrientDriftRecord, one per metric with data (may be empty).
        """
        raw = await storage.get_readings(_SENSOR_NUTRIENT, start, end)
        if not raw:
            return []

        # Bin readings by metric
        ph_readings: list[tuple[datetime, float]] = []
        ec_readings: list[tuple[datetime, float]] = []

        for r in raw:
            metric = (r.get("metric") or "").lower()
            val = r.get("value")
            ts = r.get("timestamp")
            if val is None or ts is None:
                continue
            if metric == _METRIC_PH:
                ph_readings.append((ts, float(val)))
            elif metric in (_METRIC_EC, "electrical_conductivity"):
                ec_readings.append((ts, float(val)))

        results: list[NutrientDriftRecord] = []
        for metric_name, readings, threshold in [
            ("pH", ph_readings, _THRESHOLD_PH),
            ("EC", ec_readings, _THRESHOLD_EC),
        ]:
            if len(readings) < 2:
                continue

            readings_sorted = sorted(readings, key=lambda x: x[0])
            timestamps, values = zip(*readings_sorted)

            t0 = timestamps[0]
            # Convert timestamps to elapsed days from the first reading
            days = np.array(
                [(ts - t0).total_seconds() / 86400 for ts in timestamps],
                dtype=float,
            )
            vals = np.array(values, dtype=float)

            # Linear regression: drift_rate = slope of best-fit line (units/day)
            if days[-1] == 0:
                drift_rate = 0.0
            else:
                slope, _ = np.polyfit(days, vals, 1)
                drift_rate = float(slope)

            period_days = float(days[-1]) if days[-1] > 0 else 0.0

            results.append(
                NutrientDriftRecord(
                    grow_id=grow_id,
                    metric=metric_name,
                    start_value=float(vals[0]),
                    end_value=float(vals[-1]),
                    drift_rate=round(drift_rate, 6),
                    period_days=round(period_days, 4),
                    flagged=abs(drift_rate) > threshold,
                )
            )

        return results
