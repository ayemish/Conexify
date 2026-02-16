"""
ETL / Scheduled Data Loading Pipeline

Provides scheduled and on-demand data loading from:
- CSV file directories (watch folder pattern)
- Demo data generator output (JSON files)
- Database-to-database transfers

Can be run as a standalone cron job or integrated into the FastAPI
application as a background task scheduler.
"""

import asyncio
import csv
import glob
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineRunResult:
    """Result from a single pipeline run."""
    run_id: str
    status: PipelineStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_loaded: int = 0
    records_failed: int = 0
    assets_seen: List[str] = field(default_factory=list)
    files_processed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class ETLConfig:
    """Configuration for the ETL pipeline."""
    # Watch folder for CSV drops
    csv_watch_dir: str = ""
    csv_archive_dir: str = ""
    csv_glob_pattern: str = "*.csv"

    # Demo data JSON directory
    demo_data_dir: str = ""

    # Schedule
    poll_interval_seconds: float = 300.0  # 5 minutes
    enabled: bool = True

    # Processing
    batch_size: int = 500
    site_id: str = "default"

    # File handling
    archive_processed: bool = True
    delete_after_processing: bool = False


class ETLPipeline:
    """Scheduled ETL pipeline for batch telemetry loading.

    Modes:
    1. **Watch folder**: Monitors a directory for CSV files, loads them,
       and archives/deletes after processing.
    2. **Demo ingest**: Loads pre-generated demo JSON files into the
       PdM pipeline for demonstration.
    3. **On-demand**: Can be triggered via API for ad-hoc loads.
    """

    def __init__(self, config: Optional[ETLConfig] = None):
        self.config = config or ETLConfig()
        self._running = False
        self._current_status = PipelineStatus.IDLE
        self._history: List[PipelineRunResult] = []
        self._stats = {
            "total_runs": 0,
            "total_records": 0,
            "total_failures": 0,
            "last_run_at": None,
        }

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "status": self._current_status.value,
            "running": self._running,
            "stats": self._stats,
            "history_count": len(self._history),
        }

    # ── CSV Loading ───────────────────────────────────────────────────

    def _load_csv_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Parse a CSV file into telemetry records."""
        records = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    asset_id = (
                        row.get("asset_id") or row.get("AssetID") or
                        row.get("unit_id") or row.get("device_id") or ""
                    ).strip()
                    ts_raw = (
                        row.get("timestamp") or row.get("Timestamp") or
                        row.get("datetime") or row.get("time") or ""
                    ).strip()

                    if not asset_id or not ts_raw:
                        continue

                    ts = None
                    for fmt in [
                        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                        "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M",
                    ]:
                        try:
                            ts = datetime.strptime(ts_raw, fmt)
                            break
                        except ValueError:
                            continue
                    if ts is None:
                        continue

                    record = {
                        "asset_id": asset_id,
                        "site_id": row.get("site_id", self.config.site_id),
                        "timestamp": ts,
                    }

                    # Flexible field mapping
                    float_fields = {
                        "suction_pressure": ["suction_pressure", "SuctionPressure"],
                        "discharge_pressure": ["discharge_pressure", "DischargePressure"],
                        "suction_line_temp": ["suction_line_temp", "suction_temp", "SuctionTemp"],
                        "discharge_temp": ["discharge_temp", "DischargeTemp"],
                        "supply_air_temp": ["supply_air_temp", "SupplyAirTemp", "SAT"],
                        "return_air_temp": ["return_air_temp", "ReturnAirTemp", "RAT"],
                        "ambient_temp": ["ambient_temp", "AmbientTemp", "OAT"],
                        "zone_temp": ["zone_temp", "ZoneTemp", "SpaceTemp"],
                        "compressor_current": ["compressor_current", "CompressorCurrent"],
                        "compressor_power": ["compressor_power", "CompressorPower"],
                        "superheat": ["superheat", "SH"],
                        "subcool": ["subcool", "SC"],
                    }
                    for target, sources in float_fields.items():
                        for src in sources:
                            val = row.get(src)
                            if val is not None and str(val).strip():
                                try:
                                    record[target] = float(val)
                                except (ValueError, TypeError):
                                    pass
                                break

                    # Boolean fields
                    for src in ["compressor_on", "CompressorOn"]:
                        val = row.get(src)
                        if val is not None:
                            record["compressor_on"] = str(val).strip().lower() in ("1", "true", "on", "yes")
                            break

                    records.append(record)
                except Exception as e:
                    logger.debug("CSV row parse error: %s", e)

        return records

    # ── Demo JSON Loading ─────────────────────────────────────────────

    def _load_demo_json(self, filepath: str) -> List[Dict[str, Any]]:
        """Load pre-generated demo data JSON."""
        records = []
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "readings" in data:
                items = data["readings"]
            else:
                items = [data]

            for item in items:
                if "asset_id" in item and "timestamp" in item:
                    ts = item["timestamp"]
                    if isinstance(ts, str):
                        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
                            try:
                                ts = datetime.strptime(ts, fmt)
                                break
                            except ValueError:
                                continue
                    item["timestamp"] = ts
                    records.append(item)
        except Exception as e:
            logger.error("Demo JSON load failed for %s: %s", filepath, e)

        return records

    # ── Persistence ───────────────────────────────────────────────────

    def _persist_batch(self, records: List[Dict[str, Any]]) -> int:
        """Persist a batch of records to the database."""
        persisted = 0
        try:
            from ..persistence.database import get_session
            from ..persistence.repositories import TelemetryRepository, AssetRepository

            with get_session() as session:
                asset_repo = AssetRepository(session)
                telem_repo = TelemetryRepository(session)

                # Ensure all assets exist
                seen_assets = set()
                for r in records:
                    aid = r.get("asset_id", "")
                    if aid and aid not in seen_assets:
                        existing = asset_repo.get_by_id(aid)
                        if not existing:
                            asset_repo.create(
                                asset_id=aid,
                                site_id=r.get("site_id", self.config.site_id),
                            )
                        seen_assets.add(aid)

                # Bulk insert
                db_records = []
                for r in records:
                    db_rec = {k: v for k, v in r.items() if k != "site_id"}
                    db_records.append(db_rec)

                if db_records:
                    persisted = telem_repo.bulk_create(db_records)

                session.commit()
        except Exception as e:
            logger.warning("Batch persistence failed: %s", e)

        return persisted

    # ── PdM Processing ────────────────────────────────────────────────

    def _process_through_pdm(self, records: List[Dict[str, Any]]) -> int:
        """Feed records through the PdM pipeline."""
        processed = 0
        try:
            from ..api.routes import get_pdm_system
            for r in records:
                aid = r.get("asset_id", "")
                try:
                    system = get_pdm_system(aid)
                    if system:
                        system.process_reading(r)
                        processed += 1
                except Exception:
                    pass
        except Exception as e:
            logger.debug("PdM processing unavailable: %s", e)
        return processed

    # ── Pipeline Execution ────────────────────────────────────────────

    def run_once(self) -> PipelineRunResult:
        """Execute a single pipeline run (synchronous)."""
        import uuid
        run_id = f"ETL-{uuid.uuid4().hex[:8].upper()}"
        started = datetime.utcnow()
        self._current_status = PipelineStatus.RUNNING

        result = PipelineRunResult(
            run_id=run_id,
            status=PipelineStatus.RUNNING,
            started_at=started,
        )

        all_records: List[Dict[str, Any]] = []
        assets_seen = set()

        # Phase 1: Discover and load CSV files
        if self.config.csv_watch_dir and os.path.isdir(self.config.csv_watch_dir):
            pattern = os.path.join(self.config.csv_watch_dir, self.config.csv_glob_pattern)
            csv_files = sorted(glob.glob(pattern))

            for filepath in csv_files:
                try:
                    records = self._load_csv_file(filepath)
                    all_records.extend(records)
                    result.files_processed.append(filepath)

                    # Archive or delete
                    if self.config.archive_processed and self.config.csv_archive_dir:
                        os.makedirs(self.config.csv_archive_dir, exist_ok=True)
                        dest = os.path.join(
                            self.config.csv_archive_dir,
                            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(filepath)}"
                        )
                        os.rename(filepath, dest)
                    elif self.config.delete_after_processing:
                        os.remove(filepath)

                except Exception as e:
                    result.errors.append(f"CSV {filepath}: {e}")
                    result.records_failed += 1

        # Phase 2: Load demo JSON files
        if self.config.demo_data_dir and os.path.isdir(self.config.demo_data_dir):
            json_files = sorted(glob.glob(os.path.join(self.config.demo_data_dir, "demo_*.json")))
            for filepath in json_files:
                try:
                    records = self._load_demo_json(filepath)
                    all_records.extend(records)
                    result.files_processed.append(filepath)
                except Exception as e:
                    result.errors.append(f"JSON {filepath}: {e}")

        # Phase 3: Persist and process
        if all_records:
            for r in all_records:
                assets_seen.add(r.get("asset_id", ""))

            # Batch persist
            for i in range(0, len(all_records), self.config.batch_size):
                batch = all_records[i : i + self.config.batch_size]
                persisted = self._persist_batch(batch)
                result.records_loaded += persisted

            # Feed through PdM (sample for performance)
            sample = all_records[:200]
            self._process_through_pdm(sample)

        # Finalize
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - started).total_seconds()
        result.assets_seen = sorted(assets_seen - {""})
        result.status = PipelineStatus.COMPLETED if not result.errors else PipelineStatus.FAILED

        self._current_status = result.status
        self._history.append(result)
        if len(self._history) > 100:
            self._history = self._history[-50:]

        self._stats["total_runs"] += 1
        self._stats["total_records"] += result.records_loaded
        self._stats["total_failures"] += result.records_failed
        self._stats["last_run_at"] = result.completed_at.isoformat()

        logger.info(
            "ETL run %s: %d records loaded from %d files in %.1fs",
            run_id, result.records_loaded, len(result.files_processed), result.duration_seconds,
        )

        return result

    async def run_scheduled(self):
        """Run the pipeline on a schedule (async loop)."""
        self._running = True
        logger.info(
            "ETL scheduler started (interval=%.0fs, csv_dir=%s, demo_dir=%s)",
            self.config.poll_interval_seconds,
            self.config.csv_watch_dir or "(none)",
            self.config.demo_data_dir or "(none)",
        )

        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.error("ETL scheduled run failed: %s", e, exc_info=True)

            await asyncio.sleep(self.config.poll_interval_seconds)

    def stop(self):
        """Stop the scheduled pipeline."""
        self._running = False
        logger.info("ETL scheduler stopped")

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent pipeline run history."""
        return [
            {
                "run_id": r.run_id,
                "status": r.status.value,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "records_loaded": r.records_loaded,
                "records_failed": r.records_failed,
                "assets_seen": r.assets_seen,
                "files_processed": r.files_processed,
                "errors": r.errors,
                "duration_seconds": r.duration_seconds,
            }
            for r in reversed(self._history[-limit:])
        ]
