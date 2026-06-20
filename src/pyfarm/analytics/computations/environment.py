"""Environment KPI computations for pyfarm-analytics."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from pyfarm.analytics.models import AnomalyRecord, EnvironmentSummary

if TYPE_CHECKING:
    from pyfarm.storage.backend import StorageBackend

# Sensor metric name constants (matched against SensorReading.metric)
_METRIC_TEMP = "temperature"
_METRIC_RH = "humidity"
_METRIC_VPD = "vpd"
_METRIC_CO2 = "co2"
_METRIC_PPFD = "ppfd"  # Photosynthetic Photon Flux Density — for DLI

# Canonical sensor_ids used when querying storage.
# These are the logical sensor IDs registered per grow.
_SENSOR_ENV = "env"  # Covers temp, RH, VPD, CO2 readings
_SENSOR_LIGHT = "light"

# DLI conversion: average PPFD (μmol/m²/s) * photoperiod_hours * 3600 / 1_000_000
_PHOTOPERIOD_HOURS = 18  # default photoperiod assumption (hours/day)


class EnvironmentAnalyzer:
    """Computes environment KPIs from raw sensor readings."""

    async def compute_summary(
        self,
        storage: "StorageBackend",
        grow_id: str,
        start: datetime,
        end: datetime,
        stage: str = "unknown",
    ) -> EnvironmentSummary:
        """Compute aggregated environment summary over the given period.

        Queries the storage backend for temperature, relative humidity, VPD,
        CO2, and light readings, then returns averaged values.  DLI is estimated
        from mean PPFD when light readings are available.

        Args:
            storage: Async StorageBackend instance.
            grow_id:  Identifier for the grow session.
            start:    Period start (UTC-aware datetime).
            end:      Period end (UTC-aware datetime).
            stage:    Growth stage label (e.g. "vegetative", "flowering").

        Returns:
            EnvironmentSummary with averaged metrics; zero-filled where no data.
        """
        # Pull raw readings for the environmental sensor
        raw = await storage.get_readings(_SENSOR_ENV, start, end)

        temps, rhs, vpds, co2s = [], [], [], []
        for r in raw:
            metric = (r.get("metric") or "").lower()
            val = r.get("value")
            if val is None:
                continue
            if metric == _METRIC_TEMP:
                temps.append(float(val))
            elif metric in (_METRIC_RH, "relative_humidity"):
                rhs.append(float(val))
            elif metric == _METRIC_VPD:
                vpds.append(float(val))
            elif metric == _METRIC_CO2:
                co2s.append(float(val))

        def _mean(lst: list[float]) -> float:
            return float(np.mean(lst)) if lst else 0.0

        mean_temp = _mean(temps)
        mean_rh = _mean(rhs)
        mean_vpd = _mean(vpds)
        mean_co2 = _mean(co2s)

        # Attempt DLI estimation from light sensor (PPFD readings)
        dli = 0.0
        light_raw = await storage.get_readings(_SENSOR_LIGHT, start, end)
        ppfds = []
        for r in light_raw:
            metric = (r.get("metric") or "").lower()
            val = r.get("value")
            if val is None:
                continue
            if metric in (_METRIC_PPFD, "light", "ppfd"):
                ppfds.append(float(val))
        if ppfds:
            mean_ppfd = float(np.mean(ppfds))
            # DLI (mol/m²/day) = PPFD (μmol/m²/s) × photoperiod_s / 1_000_000
            dli = mean_ppfd * _PHOTOPERIOD_HOURS * 3600 / 1_000_000

        return EnvironmentSummary(
            grow_id=grow_id,
            stage=stage,
            period_start=start,
            period_end=end,
            mean_temp=mean_temp,
            mean_rh=mean_rh,
            mean_vpd=mean_vpd,
            mean_co2=mean_co2,
            dli=round(dli, 4),
        )

    async def detect_anomalies(
        self,
        storage: "StorageBackend",
        grow_id: str,
        sensor_id: str,
        start: datetime,
        end: datetime,
        threshold: float = 3.0,
    ) -> list[AnomalyRecord]:
        """Detect anomalous readings using z-score analysis.

        Readings whose absolute z-score exceeds *threshold* are returned as
        AnomalyRecord objects.

        Args:
            storage:   Async StorageBackend instance.
            grow_id:   Grow session identifier.
            sensor_id: Sensor to analyse.
            start:     Period start.
            end:       Period end.
            threshold: Z-score threshold; readings above this are flagged.

        Returns:
            List of AnomalyRecord (may be empty).
        """
        raw = await storage.get_readings(sensor_id, start, end)
        if len(raw) < 2:
            return []

        values = np.array([float(r["value"]) for r in raw], dtype=float)
        std = np.std(values)
        if std == 0:
            return []

        zscores = np.abs((values - np.mean(values)) / std)
        anomalies: list[AnomalyRecord] = []
        for idx, row in enumerate(raw):
            if zscores[idx] > threshold:
                anomalies.append(
                    AnomalyRecord(
                        grow_id=grow_id,
                        sensor_id=sensor_id,
                        metric=row.get("metric", ""),
                        timestamp=row["timestamp"],
                        value=float(row["value"]),
                        zscore=float(zscores[idx]),
                        threshold=threshold,
                    )
                )
        return anomalies
