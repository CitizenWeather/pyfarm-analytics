"""Top-level Analyzer class for pyfarm-analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pyfarm.analytics.computations.environment import EnvironmentAnalyzer
from pyfarm.analytics.computations.nutrients import NutrientAnalyzer
from pyfarm.analytics.models import (
    AnomalyRecord,
    EnvironmentSummary,
    KPIDashboard,
    NutrientDriftRecord,
)

if TYPE_CHECKING:
    from pyfarm.storage.backend import StorageBackend


class Analyzer:
    """High-level analytics interface backed by a StorageBackend.

    All public methods are async and delegate to the specialised computation
    modules in ``pyfarm.analytics.computations``.

    Args:
        storage: Any object conforming to the ``StorageBackend`` protocol
                 (from ``pyfarm.storage``).

    Example::

        from pyfarm.storage import get_backend
        from pyfarm.analytics import Analyzer

        storage = get_backend()
        analyzer = Analyzer(storage)
        summary = await analyzer.environment_summary(grow_id, start, end)
    """

    def __init__(self, storage: "StorageBackend") -> None:
        self._storage = storage
        self._env = EnvironmentAnalyzer()
        self._nutrients = NutrientAnalyzer()

    async def environment_summary(
        self,
        grow_id: str,
        start: datetime,
        end: datetime,
        stage: str = "unknown",
    ) -> EnvironmentSummary:
        """Return an aggregated environment summary for the period.

        Args:
            grow_id: Grow session identifier.
            start:   Period start (UTC-aware datetime).
            end:     Period end (UTC-aware datetime).
            stage:   Growth stage label.

        Returns:
            EnvironmentSummary with averaged temperature, RH, VPD, CO2, DLI.
        """
        return await self._env.compute_summary(
            self._storage, grow_id, start, end, stage=stage
        )

    async def nutrient_drift(
        self,
        grow_id: str,
        start: datetime,
        end: datetime,
    ) -> list[NutrientDriftRecord]:
        """Return nutrient drift records for pH and EC over the period.

        Args:
            grow_id: Grow session identifier.
            start:   Period start.
            end:     Period end.

        Returns:
            List of NutrientDriftRecord, flagged when drift exceeds thresholds.
        """
        return await self._nutrients.compute_drift(
            self._storage, grow_id, start, end
        )

    async def anomalies(
        self,
        grow_id: str,
        sensor_id: str,
        start: datetime,
        end: datetime,
        threshold: float = 3.0,
    ) -> list[AnomalyRecord]:
        """Detect anomalous sensor readings using z-score analysis.

        Args:
            grow_id:   Grow session identifier.
            sensor_id: Sensor to analyse.
            start:     Period start.
            end:       Period end.
            threshold: Z-score threshold (default 3.0).

        Returns:
            List of AnomalyRecord for readings exceeding the threshold.
        """
        return await self._env.detect_anomalies(
            self._storage, grow_id, sensor_id, start, end, threshold=threshold
        )

    async def dashboard(
        self,
        grow_id: str,
        start: datetime,
        end: datetime,
    ) -> KPIDashboard:
        """Build a full KPI dashboard for the given grow and period.

        Runs environment summary, nutrient drift, and anomaly detection
        concurrently (sequentially for now; can be parallelised with
        asyncio.gather if the backend supports concurrent queries).

        Args:
            grow_id: Grow session identifier.
            start:   Period start.
            end:     Period end.

        Returns:
            KPIDashboard aggregating all computed KPIs.
        """
        env_summary = await self.environment_summary(grow_id, start, end)
        nutrient_records = await self.nutrient_drift(grow_id, start, end)
        anomaly_records = await self.anomalies(grow_id, "env", start, end)

        return KPIDashboard(
            grow_id=grow_id,
            as_of=datetime.now(timezone.utc),
            yield_summary={},
            environment_summary=env_summary,
            anomalies=anomaly_records,
            nutrient_drifts=nutrient_records,
        )
