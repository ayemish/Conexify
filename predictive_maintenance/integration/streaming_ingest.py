"""
MQTT / BACnet Streaming Ingest Service

Provides real-time telemetry ingestion from:
- MQTT brokers (common for IoT/BMS gateways)
- BACnet/IP networks (native building automation protocol)

Ingested readings are forwarded to the PdM pipeline and broadcast
to WebSocket clients for live dashboard updates.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Protocol adapters ─────────────────────────────────────────────────

class IngestProtocol(str, Enum):
    MQTT = "mqtt"
    BACNET = "bacnet"


@dataclass
class IngestConfig:
    """Configuration for a streaming ingest source."""
    protocol: IngestProtocol = IngestProtocol.MQTT
    # MQTT settings
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topics: List[str] = field(default_factory=lambda: ["bms/+/telemetry", "hvac/+/sensors"])
    mqtt_qos: int = 1
    mqtt_client_id: str = "pdm-ingest"
    # BACnet settings
    bacnet_interface: str = "0.0.0.0"
    bacnet_port: int = 47808
    bacnet_device_ids: List[int] = field(default_factory=list)
    bacnet_poll_interval_seconds: float = 60.0
    # Common
    site_id: str = "default"
    batch_size: int = 50
    flush_interval_seconds: float = 5.0


# ── MQTT Adapter ──────────────────────────────────────────────────────

class MQTTIngestAdapter:
    """Subscribes to MQTT topics and converts messages to telemetry dicts."""

    def __init__(self, config: IngestConfig, on_readings: Callable):
        self.config = config
        self.on_readings = on_readings
        self._client = None
        self._running = False
        self._buffer: List[Dict[str, Any]] = []
        self._last_flush = time.monotonic()

    async def start(self):
        """Connect to MQTT broker and begin subscribing."""
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except ImportError:
            logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
            return

        self._running = True
        client = mqtt.Client(
            client_id=self.config.mqtt_client_id,
            protocol=mqtt.MQTTv5,
        )

        if self.config.mqtt_username:
            client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        try:
            client.connect(self.config.mqtt_broker, self.config.mqtt_port, keepalive=60)
            self._client = client
            logger.info(
                "MQTT connected to %s:%d", self.config.mqtt_broker, self.config.mqtt_port
            )
            # Run network loop in a thread
            client.loop_start()

            # Periodic flush loop
            while self._running:
                await asyncio.sleep(self.config.flush_interval_seconds)
                await self._flush_buffer()

        except Exception as e:
            logger.error("MQTT connection failed: %s", e)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        for topic in self.config.mqtt_topics:
            client.subscribe(topic, qos=self.config.mqtt_qos)
            logger.info("Subscribed to MQTT topic: %s", topic)

    def _on_message(self, client, userdata, msg):
        """Parse incoming MQTT message into a telemetry dict."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))

            # Extract asset_id from topic (e.g. bms/<asset_id>/telemetry)
            parts = msg.topic.split("/")
            asset_id = payload.get("asset_id") or (parts[1] if len(parts) >= 2 else "unknown")

            reading = {
                "asset_id": asset_id,
                "site_id": payload.get("site_id", self.config.site_id),
                "timestamp": payload.get("timestamp", datetime.utcnow().isoformat()),
            }

            # Map common BMS field names
            field_map = {
                "suction_pressure": ["suction_pressure", "SuctionPressure", "sp"],
                "discharge_pressure": ["discharge_pressure", "DischargePressure", "dp"],
                "suction_line_temp": ["suction_line_temp", "suction_temp", "SuctionTemp"],
                "discharge_temp": ["discharge_temp", "DischargeTemp"],
                "supply_air_temp": ["supply_air_temp", "SupplyAirTemp", "SAT"],
                "return_air_temp": ["return_air_temp", "ReturnAirTemp", "RAT"],
                "ambient_temp": ["ambient_temp", "AmbientTemp", "OAT"],
                "zone_temp": ["zone_temp", "ZoneTemp", "SpaceTemp"],
                "compressor_current": ["compressor_current", "CompressorCurrent"],
                "compressor_power": ["compressor_power", "CompressorPower"],
                "compressor_on": ["compressor_on", "CompressorOn"],
                "superheat": ["superheat", "SH"],
                "subcool": ["subcool", "SC"],
            }

            for target, sources in field_map.items():
                for src in sources:
                    if src in payload:
                        val = payload[src]
                        if target == "compressor_on":
                            reading[target] = str(val).lower() in ("1", "true", "on")
                        else:
                            try:
                                reading[target] = float(val)
                            except (ValueError, TypeError):
                                pass
                        break

            self._buffer.append(reading)

            if len(self._buffer) >= self.config.batch_size:
                asyncio.get_event_loop().create_task(self._flush_buffer())

        except Exception as e:
            logger.debug("MQTT message parse error: %s", e)

    async def _flush_buffer(self):
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush = time.monotonic()
        try:
            await self.on_readings(batch)
        except Exception as e:
            logger.error("Failed to process MQTT batch (%d readings): %s", len(batch), e)

    async def stop(self):
        self._running = False
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT client disconnected")


# ── BACnet Adapter ────────────────────────────────────────────────────

class BACnetIngestAdapter:
    """Polls BACnet/IP devices for telemetry readings."""

    def __init__(self, config: IngestConfig, on_readings: Callable):
        self.config = config
        self.on_readings = on_readings
        self._running = False

    async def start(self):
        """Begin BACnet polling loop."""
        try:
            import BAC0  # type: ignore
        except ImportError:
            logger.error("BAC0 not installed. Run: pip install BAC0")
            return

        self._running = True
        try:
            bacnet = BAC0.lite(ip=self.config.bacnet_interface, port=self.config.bacnet_port)
            logger.info("BACnet/IP initialized on %s:%d", self.config.bacnet_interface, self.config.bacnet_port)
        except Exception as e:
            logger.error("BACnet initialization failed: %s", e)
            return

        while self._running:
            readings = []
            for device_id in self.config.bacnet_device_ids:
                try:
                    reading = self._poll_device(bacnet, device_id)
                    if reading:
                        readings.append(reading)
                except Exception as e:
                    logger.debug("BACnet poll failed for device %d: %s", device_id, e)

            if readings:
                try:
                    await self.on_readings(readings)
                except Exception as e:
                    logger.error("Failed to process BACnet batch: %s", e)

            await asyncio.sleep(self.config.bacnet_poll_interval_seconds)

    def _poll_device(self, bacnet, device_id: int) -> Optional[Dict[str, Any]]:
        """Read analog values from a BACnet device."""
        reading = {
            "asset_id": f"bacnet-{device_id}",
            "site_id": self.config.site_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Standard HVAC BACnet object mappings
        object_map = {
            "supply_air_temp": ("analogInput", 1),
            "return_air_temp": ("analogInput", 2),
            "discharge_temp": ("analogInput", 3),
            "suction_pressure": ("analogInput", 4),
            "discharge_pressure": ("analogInput", 5),
            "compressor_current": ("analogInput", 6),
            "zone_temp": ("analogInput", 7),
            "ambient_temp": ("analogInput", 8),
        }

        values_read = 0
        for field_name, (obj_type, obj_instance) in object_map.items():
            try:
                val = bacnet.read(f"{device_id} {obj_type} {obj_instance} presentValue")
                if val is not None:
                    reading[field_name] = float(val)
                    values_read += 1
            except Exception:
                pass

        return reading if values_read > 0 else None

    async def stop(self):
        self._running = False
        logger.info("BACnet adapter stopped")


# ── Streaming Ingest Service ──────────────────────────────────────────

class StreamingIngestService:
    """Orchestrates streaming ingest from MQTT and/or BACnet sources.

    Ingested data is:
    1. Persisted to the database (if available)
    2. Fed through the PdM pipeline
    3. Broadcast to WebSocket clients
    """

    def __init__(self, configs: Optional[List[IngestConfig]] = None):
        self.configs = configs or []
        self._adapters: List[Any] = []
        self._running = False
        self._stats = {
            "readings_received": 0,
            "readings_processed": 0,
            "readings_failed": 0,
            "batches_processed": 0,
        }

    async def _handle_readings(self, readings: List[Dict[str, Any]]):
        """Process a batch of incoming telemetry readings."""
        self._stats["readings_received"] += len(readings)
        self._stats["batches_processed"] += 1

        for reading in readings:
            asset_id = reading.get("asset_id", "")
            try:
                # 1. Feed through PdM system
                try:
                    from .advanced_system import create_pdm_system
                    # Use the shared systems cache from routes
                    from ..api.routes import _pdm_systems, get_pdm_system
                    system = _pdm_systems.get(asset_id)
                    if not system:
                        system = get_pdm_system(asset_id)
                    if system:
                        system.process_reading(reading)
                except Exception as e:
                    logger.debug("PdM processing skipped for %s: %s", asset_id, e)

                # 2. Broadcast via WebSocket
                try:
                    from ..api.websocket import broadcast_telemetry_update
                    await broadcast_telemetry_update(asset_id, reading)
                except Exception as e:
                    logger.debug("WebSocket broadcast skipped: %s", e)

                # 3. Persist to database
                try:
                    from ..persistence.database import get_session
                    from ..persistence.repositories import TelemetryRepository, AssetRepository

                    ts = reading.get("timestamp")
                    if isinstance(ts, str):
                        from datetime import datetime as dt
                        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]:
                            try:
                                ts = dt.strptime(ts, fmt)
                                break
                            except ValueError:
                                continue

                    with get_session() as session:
                        asset_repo = AssetRepository(session)
                        if not asset_repo.get_by_id(asset_id):
                            asset_repo.create(
                                asset_id=asset_id,
                                site_id=reading.get("site_id", "default"),
                            )
                        telem_repo = TelemetryRepository(session)
                        telem_repo.create(asset_id=asset_id, timestamp=ts, **{
                            k: v for k, v in reading.items()
                            if k not in ("asset_id", "site_id", "timestamp")
                        })
                        session.commit()
                except Exception as e:
                    logger.debug("Persistence skipped for %s: %s", asset_id, e)

                self._stats["readings_processed"] += 1

            except Exception as e:
                self._stats["readings_failed"] += 1
                logger.error("Failed to process reading for %s: %s", asset_id, e)

    async def start(self):
        """Start all configured ingest adapters."""
        self._running = True
        tasks = []

        for config in self.configs:
            if config.protocol == IngestProtocol.MQTT:
                adapter = MQTTIngestAdapter(config, self._handle_readings)
            elif config.protocol == IngestProtocol.BACNET:
                adapter = BACnetIngestAdapter(config, self._handle_readings)
            else:
                logger.warning("Unknown ingest protocol: %s", config.protocol)
                continue

            self._adapters.append(adapter)
            tasks.append(asyncio.create_task(adapter.start()))

        logger.info("Streaming ingest started with %d adapter(s)", len(self._adapters))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        """Stop all adapters."""
        self._running = False
        for adapter in self._adapters:
            await adapter.stop()
        logger.info("Streaming ingest stopped. Stats: %s", self._stats)

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)
