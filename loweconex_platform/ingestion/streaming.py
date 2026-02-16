"""
Streaming Ingest Service — MQTT and BACnet real-time data ingestion.

Provides protocol-specific listeners that normalize incoming telemetry
into canonical TwinStore time-series points and operational events,
publishing to the Redis event bus for downstream consumers.

Usage:
    from loweconex_platform.ingestion.streaming import StreamingIngestService
    svc = StreamingIngestService()
    svc.start()   # starts background listener threads
    svc.stop()
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Optional dependency detection ───────────────────────────────────

_MQTT_AVAILABLE = False
try:
    import paho.mqtt.client as mqtt  # type: ignore
    _MQTT_AVAILABLE = True
except ImportError:
    mqtt = None  # type: ignore

_BACNET_AVAILABLE = False
try:
    import BAC0  # type: ignore
    _BACNET_AVAILABLE = True
except ImportError:
    BAC0 = None  # type: ignore


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class StreamConfig:
    """Configuration for a streaming data source."""
    protocol: str  # "mqtt" or "bacnet"
    enabled: bool = True

    # MQTT settings
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topics: List[str] = field(default_factory=lambda: ["pdm/telemetry/#", "pdm/events/#"])
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: str = "pdm_ingest"
    mqtt_qos: int = 1

    # BACnet settings
    bacnet_ip: str = "0.0.0.0"
    bacnet_port: int = 47808
    bacnet_device_ids: List[int] = field(default_factory=list)
    bacnet_poll_interval_seconds: float = 30.0

    # Processing
    batch_size: int = 100
    flush_interval_seconds: float = 5.0

    # Backpressure: max queued messages before dropping
    high_water_mark: int = 10_000


@dataclass
class IngestMetrics:
    """Runtime metrics for the streaming ingest service."""
    messages_received: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    backpressure_drops: int = 0
    last_message_ts: Optional[str] = None
    uptime_seconds: float = 0.0
    active_protocols: List[str] = field(default_factory=list)
    queue_depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "messages_failed": self.messages_failed,
            "backpressure_drops": self.backpressure_drops,
            "last_message_ts": self.last_message_ts,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "active_protocols": self.active_protocols,
            "queue_depth": self.queue_depth,
        }


# ── MQTT Listener ───────────────────────────────────────────────────

class MQTTListener:
    """MQTT subscription listener that normalizes messages into TwinStore."""

    def __init__(self, config: StreamConfig, message_handler: Callable):
        self.config = config
        self._handler = message_handler
        self._client: Optional[Any] = None
        self._running = False

    def start(self):
        if not _MQTT_AVAILABLE:
            logger.warning("MQTT listener: paho-mqtt not installed — skipping")
            return
        self._running = True
        self._client = mqtt.Client(client_id=self.config.mqtt_client_id)
        if self.config.mqtt_username:
            self._client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(self.config.mqtt_broker, self.config.mqtt_port, keepalive=60)
            self._client.loop_start()
            logger.info(
                "MQTT listener started: %s:%d topics=%s",
                self.config.mqtt_broker, self.config.mqtt_port, self.config.mqtt_topics,
            )
        except Exception as e:
            logger.error("MQTT connect failed: %s", e)
            self._running = False

    def stop(self):
        self._running = False
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT listener stopped")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            for topic in self.config.mqtt_topics:
                client.subscribe(topic, qos=self.config.mqtt_qos)
                logger.debug("Subscribed to MQTT topic: %s", topic)
        else:
            logger.error("MQTT connect returned code %d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self._handler("mqtt", msg.topic, payload)
        except Exception as e:
            logger.debug("MQTT message parse error on %s: %s", msg.topic, e)

    def _on_disconnect(self, client, userdata, rc):
        if self._running:
            logger.warning("MQTT disconnected (rc=%d), will auto-reconnect", rc)


# ── BACnet Poller ───────────────────────────────────────────────────

class BACnetPoller:
    """BACnet/IP polling listener that reads object values on an interval."""

    def __init__(self, config: StreamConfig, message_handler: Callable):
        self.config = config
        self._handler = message_handler
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._network: Optional[Any] = None

    def start(self):
        if not _BACNET_AVAILABLE:
            logger.warning("BACnet poller: BAC0 not installed — skipping")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="bacnet-poller")
        self._thread.start()
        logger.info("BACnet poller started (interval=%0.1fs)", self.config.bacnet_poll_interval_seconds)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._network:
            try:
                self._network.disconnect()
            except Exception:
                pass
        logger.info("BACnet poller stopped")

    def _poll_loop(self):
        try:
            self._network = BAC0.lite(ip=self.config.bacnet_ip, port=self.config.bacnet_port)
        except Exception as e:
            logger.error("BACnet network init failed: %s", e)
            self._running = False
            return

        while self._running:
            for device_id in self.config.bacnet_device_ids:
                try:
                    self._read_device(device_id)
                except Exception as e:
                    logger.debug("BACnet read error for device %d: %s", device_id, e)
            time.sleep(self.config.bacnet_poll_interval_seconds)

    def _read_device(self, device_id: int):
        """Read common HVAC BACnet objects from a device."""
        points = [
            ("analogInput", 0, "zone_temp"),
            ("analogInput", 1, "supply_air_temp"),
            ("analogInput", 2, "return_air_temp"),
            ("analogInput", 3, "discharge_pressure"),
            ("analogInput", 4, "suction_pressure"),
            ("analogOutput", 0, "compressor_speed"),
            ("binaryInput", 0, "compressor_status"),
        ]
        for obj_type, obj_instance, metric_name in points:
            try:
                value = self._network.read(f"{device_id} {obj_type} {obj_instance} presentValue")
                if value is not None:
                    self._handler("bacnet", f"device/{device_id}/{metric_name}", {
                        "asset_id": f"bacnet_{device_id}",
                        "metric": metric_name,
                        "value": float(value) if not isinstance(value, str) else value,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except Exception:
                pass


# ── Streaming Ingest Service ────────────────────────────────────────

class StreamingIngestService:
    """Unified streaming ingest service managing MQTT and BACnet listeners.

    Normalizes incoming data into TwinStore time-series points,
    publishes events to the Redis event bus, and forwards readings
    to the PdM kernel (HVACRPdMAdvancedSystem) for real-time health
    assessment, fault diagnosis, and RUL estimation.
    """

    def __init__(self, configs: Optional[List[StreamConfig]] = None):
        self.configs = configs or []
        self._listeners: List[Any] = []
        self.metrics = IngestMetrics()
        self._start_time: Optional[float] = None
        self._twin_store = None
        self._event_bus = None
        self._pdm_systems: Dict[str, Any] = {}
        self._pdm_available: Optional[bool] = None

        # Backpressure: bounded queue between listeners and processing
        hwm = max((c.high_water_mark for c in self.configs), default=10_000)
        self._msg_queue: queue.Queue = queue.Queue(maxsize=hwm)
        self._consumer_thread: Optional[threading.Thread] = None
        self._running = False

    def _init_backends(self):
        """Lazy-init TwinStore and event bus."""
        if self._twin_store is None:
            try:
                from loweconex_platform.digital_twins.store import get_default_store
                self._twin_store = get_default_store()
            except Exception as e:
                logger.warning("TwinStore not available for streaming ingest: %s", e)

        if self._event_bus is None:
            try:
                from shared.event_bus.redis_event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except Exception:
                pass

    def _get_pdm_system(self, asset_id: str):
        """Get or create a PdM kernel system for an asset.

        Returns None if the predictive_maintenance module is not available.
        """
        if self._pdm_available is False:
            return None

        if asset_id in self._pdm_systems:
            return self._pdm_systems[asset_id]

        try:
            from predictive_maintenance.integration.advanced_system import create_pdm_system
            system = create_pdm_system(asset_id=asset_id)
            self._pdm_systems[asset_id] = system
            self._pdm_available = True
            return system
        except ImportError:
            self._pdm_available = False
            logger.info("PdM kernel not available — streaming data will not trigger real-time diagnostics")
            return None
        except Exception as e:
            logger.debug("PdM system creation failed for %s: %s", asset_id, e)
            return None

    def start(self):
        """Start all configured protocol listeners."""
        self._init_backends()
        self._start_time = time.time()
        self._running = True

        # Start consumer thread that drains the backpressure queue
        self._consumer_thread = threading.Thread(
            target=self._consume_loop, daemon=True, name="ingest-consumer",
        )
        self._consumer_thread.start()

        for cfg in self.configs:
            if not cfg.enabled:
                continue
            if cfg.protocol == "mqtt":
                listener = MQTTListener(cfg, self._enqueue_message)
                listener.start()
                self._listeners.append(listener)
                self.metrics.active_protocols.append("mqtt")
            elif cfg.protocol == "bacnet":
                listener = BACnetPoller(cfg, self._enqueue_message)
                listener.start()
                self._listeners.append(listener)
                self.metrics.active_protocols.append("bacnet")
            else:
                logger.warning("Unknown streaming protocol: %s", cfg.protocol)

        logger.info("StreamingIngestService started with %d listeners", len(self._listeners))

    def stop(self):
        """Stop all listeners and drain the queue."""
        self._running = False
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception as e:
                logger.debug("Listener stop error: %s", e)
        self._listeners.clear()
        self.metrics.active_protocols.clear()
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        logger.info("StreamingIngestService stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return current ingest metrics."""
        if self._start_time:
            self.metrics.uptime_seconds = time.time() - self._start_time
        return self.metrics.to_dict()

    def _enqueue_message(self, protocol: str, topic: str, payload: Dict[str, Any]):
        """Enqueue a message with backpressure — drop if queue is full."""
        self.metrics.messages_received += 1
        self.metrics.last_message_ts = datetime.now(timezone.utc).isoformat()
        try:
            self._msg_queue.put_nowait((protocol, topic, payload))
            self.metrics.queue_depth = self._msg_queue.qsize()
        except queue.Full:
            self.metrics.backpressure_drops += 1
            if self.metrics.backpressure_drops % 1000 == 1:
                logger.warning(
                    "Backpressure: dropped message on %s/%s (total drops=%d, queue_size=%d)",
                    protocol, topic, self.metrics.backpressure_drops, self._msg_queue.qsize(),
                )

    def _consume_loop(self):
        """Consumer thread: drain the queue and process messages."""
        while self._running:
            try:
                protocol, topic, payload = self._msg_queue.get(timeout=0.5)
                self._handle_message(protocol, topic, payload)
                self.metrics.queue_depth = self._msg_queue.qsize()
            except queue.Empty:
                continue
            except Exception as e:
                logger.debug("Consumer error: %s", e)

    def _handle_message(self, protocol: str, topic: str, payload: Dict[str, Any]):
        """Central message handler for all protocols."""
        try:
            asset_id = payload.get("asset_id") or payload.get("device_id") or ""
            timestamp_raw = payload.get("timestamp")
            if isinstance(timestamp_raw, datetime):
                timestamp = timestamp_raw
            elif isinstance(timestamp_raw, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Route to TwinStore as time-series point
            if self._twin_store and asset_id:
                from loweconex_platform.digital_twins.store import TimeSeriesPoint
                metric = payload.get("metric") or topic.split("/")[-1]
                value = payload.get("value")
                if value is not None:
                    try:
                        numeric_value = float(value)
                    except (TypeError, ValueError):
                        numeric_value = None
                    if numeric_value is not None:
                        point_id = f"{asset_id}:{metric}"
                        point = TimeSeriesPoint(
                            timestamp=timestamp,
                            value=numeric_value,
                            quality=float(payload.get("quality", 1.0) or 1.0),
                            unit=str(payload.get("unit", "") or ""),
                        )
                        self._twin_store.write_timeseries(point_id, [point])

            # Publish to event bus
            if self._event_bus:
                self._event_bus.publish(
                    f"ingest.{protocol}",
                    {"topic": topic, "asset_id": asset_id, "timestamp": timestamp.isoformat()},
                )

            # Route through PdM kernel for real-time diagnostics
            if asset_id:
                try:
                    pdm_system = self._get_pdm_system(asset_id)
                    if pdm_system is not None:
                        pdm_system.process_reading(payload)
                except Exception as pdm_err:
                    logger.debug("PdM kernel processing error for %s: %s", asset_id, pdm_err)

            self.metrics.messages_processed += 1
        except Exception as e:
            self.metrics.messages_failed += 1
            logger.debug("Streaming ingest error (%s/%s): %s", protocol, topic, e)


# ── Module-level singleton ──────────────────────────────────────────

_ingest_service: Optional[StreamingIngestService] = None


def get_ingest_service() -> StreamingIngestService:
    """Return the singleton StreamingIngestService."""
    global _ingest_service
    if _ingest_service is None:
        _ingest_service = StreamingIngestService()
    return _ingest_service
