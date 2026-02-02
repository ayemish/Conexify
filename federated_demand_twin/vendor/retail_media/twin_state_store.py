"""
Twin State Store

Persistence layer for digital twin states with:
- In-memory state management
- JSON file persistence
- History tracking with versioning
- Event emission for real-time subscriptions
"""

import json
import os
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
import threading
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.channel_state_contracts import (
    BaseTwinState,
    RMNTwinState,
    BrandTwinState,
    CampaignTwinState,
    ChannelTwinState,
    TwinType,
    TwinStateHistoryRecord,
    TwinStateEvent,
    TwinEventType,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TwinStateStoreConfig:
    """Configuration for twin state store"""
    # Persistence paths
    state_dir: str = "./data/twin_states"
    history_dir: str = "./data/twin_history"
    
    # History settings
    max_history_per_twin: int = 100
    persist_history: bool = True
    
    # Auto-save
    auto_persist: bool = True
    persist_on_update: bool = True
    
    # Event settings
    emit_events: bool = True


class TwinStateStore:
    """
    Central store for all digital twin states.
    
    Features:
    - In-memory state management for fast access
    - JSON file persistence for durability
    - Version history tracking
    - Event emission for real-time subscriptions
    """
    
    def __init__(self, config: Optional[TwinStateStoreConfig] = None):
        self.config = config or TwinStateStoreConfig()
        
        # In-memory state stores by type
        self._rmn_states: Dict[str, RMNTwinState] = {}
        self._brand_states: Dict[str, BrandTwinState] = {}
        self._campaign_states: Dict[str, CampaignTwinState] = {}
        self._channel_states: Dict[str, ChannelTwinState] = {}
        
        # History stores
        self._history: Dict[str, List[TwinStateHistoryRecord]] = defaultdict(list)
        
        # Event subscribers
        self._subscribers: Dict[str, List[Callable[[TwinStateEvent], None]]] = defaultdict(list)
        self._lock = threading.Lock()
        
        # Setup persistence directories
        self._setup_directories()
        
        # Load existing states
        self._load_states()
        
        logger.info(f"TwinStateStore initialized with state_dir={self.config.state_dir}")
    
    def _setup_directories(self):
        """Create persistence directories if they don't exist"""
        for dir_path in [self.config.state_dir, self.config.history_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            # Create subdirectories for each twin type
            for twin_type in TwinType:
                (Path(dir_path) / twin_type.value).mkdir(exist_ok=True)
    
    def _get_state_store(self, twin_type: TwinType) -> Dict[str, BaseTwinState]:
        """Get the appropriate state store for a twin type"""
        stores = {
            TwinType.RMN: self._rmn_states,
            TwinType.BRAND: self._brand_states,
            TwinType.CAMPAIGN: self._campaign_states,
            TwinType.CHANNEL: self._channel_states,
        }
        return stores[twin_type]
    
    def _get_state_class(self, twin_type: TwinType):
        """Get the state class for a twin type"""
        classes = {
            TwinType.RMN: RMNTwinState,
            TwinType.BRAND: BrandTwinState,
            TwinType.CAMPAIGN: CampaignTwinState,
            TwinType.CHANNEL: ChannelTwinState,
        }
        return classes[twin_type]
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    def update_state(
        self,
        state: BaseTwinState,
        change_reason: str = "",
        emit_event: bool = True
    ) -> BaseTwinState:
        """
        Update or create a twin state.
        
        Args:
            state: The new state to store
            change_reason: Reason for the change (for history)
            emit_event: Whether to emit state change event
            
        Returns:
            The updated state with new version
        """
        with self._lock:
            store = self._get_state_store(state.twin_type)
            twin_id = state.twin_id
            
            # Check for existing state
            existing = store.get(twin_id)
            is_new = existing is None
            
            # Compute state hash for change detection
            new_hash = state.compute_state_hash()
            
            if existing:
                old_hash = existing.compute_state_hash()
                if old_hash == new_hash:
                    logger.debug(f"No changes detected for {twin_id}, skipping update")
                    return existing
                
                # Increment version
                state.version = existing.version + 1
                state.previous_version_id = f"{twin_id}_v{existing.version}"
                
                # Compute metrics delta
                metrics_delta = self._compute_metrics_delta(existing, state)
            else:
                state.version = 1
                metrics_delta = {}
            
            # Update timestamp
            state.updated_at = datetime.utcnow()
            
            # Store a COPY of state (to prevent reference issues with hash comparison)
            state_copy = state.model_copy(deep=True)
            store[twin_id] = state_copy
            
            # Record history
            if self.config.persist_history:
                self._record_history(state, new_hash, change_reason, metrics_delta)
            
            # Persist to disk
            if self.config.auto_persist and self.config.persist_on_update:
                self._persist_state(state)
            
            # Emit event
            if self.config.emit_events and emit_event:
                event_type = TwinEventType.STATE_CREATED if is_new else TwinEventType.STATE_UPDATED
                self._emit_event(event_type, state, metrics_delta)
            
            logger.info(f"Updated {state.twin_type.value} twin {twin_id} to version {state.version}")
            return state
    
    def get_state(
        self,
        twin_id: str,
        twin_type: TwinType
    ) -> Optional[BaseTwinState]:
        """Get current state for a twin"""
        store = self._get_state_store(twin_type)
        return store.get(twin_id)
    
    def get_all_states(
        self,
        twin_type: TwinType,
        retailer_id: Optional[str] = None
    ) -> List[BaseTwinState]:
        """Get all states of a given type, optionally filtered by retailer"""
        store = self._get_state_store(twin_type)
        states = list(store.values())
        
        if retailer_id:
            states = [s for s in states if s.retailer_id == retailer_id]
        
        return states
    
    def delete_state(
        self,
        twin_id: str,
        twin_type: TwinType,
        emit_event: bool = True
    ) -> bool:
        """Delete a twin state"""
        with self._lock:
            store = self._get_state_store(twin_type)
            
            if twin_id not in store:
                return False
            
            state = store.pop(twin_id)
            
            # Remove persisted file
            state_path = self._get_state_path(twin_id, twin_type)
            if state_path.exists():
                state_path.unlink()
            
            # Emit event
            if self.config.emit_events and emit_event:
                self._emit_event(TwinEventType.STATE_DELETED, state, {})
            
            logger.info(f"Deleted {twin_type.value} twin {twin_id}")
            return True
    
    # =========================================================================
    # Bulk Operations
    # =========================================================================
    
    def update_rmn_state(self, state: RMNTwinState, **kwargs) -> RMNTwinState:
        """Update RMN twin state"""
        state.twin_type = TwinType.RMN
        return self.update_state(state, **kwargs)
    
    def update_brand_state(self, state: BrandTwinState, **kwargs) -> BrandTwinState:
        """Update Brand twin state"""
        state.twin_type = TwinType.BRAND
        return self.update_state(state, **kwargs)
    
    def update_campaign_state(self, state: CampaignTwinState, **kwargs) -> CampaignTwinState:
        """Update Campaign twin state"""
        state.twin_type = TwinType.CAMPAIGN
        return self.update_state(state, **kwargs)
    
    def update_channel_state(self, state: ChannelTwinState, **kwargs) -> ChannelTwinState:
        """Update Channel twin state"""
        state.twin_type = TwinType.CHANNEL
        return self.update_state(state, **kwargs)
    
    def get_rmn_states(self, retailer_id: Optional[str] = None) -> List[RMNTwinState]:
        """Get all RMN states"""
        return self.get_all_states(TwinType.RMN, retailer_id)
    
    def get_brand_states(self, retailer_id: Optional[str] = None) -> List[BrandTwinState]:
        """Get all Brand states"""
        return self.get_all_states(TwinType.BRAND, retailer_id)
    
    def get_campaign_states(self, retailer_id: Optional[str] = None) -> List[CampaignTwinState]:
        """Get all Campaign states"""
        return self.get_all_states(TwinType.CAMPAIGN, retailer_id)
    
    def get_channel_states(self, retailer_id: Optional[str] = None) -> List[ChannelTwinState]:
        """Get all Channel states"""
        return self.get_all_states(TwinType.CHANNEL, retailer_id)
    
    # =========================================================================
    # History Management
    # =========================================================================
    
    def _record_history(
        self,
        state: BaseTwinState,
        state_hash: str,
        change_reason: str,
        metrics_delta: Dict[str, float]
    ):
        """Record state in history"""
        record = TwinStateHistoryRecord(
            record_id=f"{state.twin_id}_v{state.version}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            twin_id=state.twin_id,
            twin_type=state.twin_type,
            version=state.version,
            state_hash=state_hash,
            state_json=json.dumps(state.dict(), default=str),
            recorded_at=datetime.utcnow(),
            source_system=state.source_system,
            change_reason=change_reason,
            metrics_delta=metrics_delta,
        )
        
        # Add to in-memory history
        history = self._history[state.twin_id]
        history.append(record)
        
        # Trim history if needed
        if len(history) > self.config.max_history_per_twin:
            history.pop(0)
        
        # Persist history record
        if self.config.persist_history:
            self._persist_history_record(record)
    
    def get_history(
        self,
        twin_id: str,
        twin_type: TwinType,
        limit: int = 50
    ) -> List[TwinStateHistoryRecord]:
        """Get state history for a twin"""
        # Try in-memory first
        if twin_id in self._history:
            history = self._history[twin_id][-limit:]
            return history
        
        # Load from disk
        return self._load_history(twin_id, twin_type, limit)
    
    def get_state_at_version(
        self,
        twin_id: str,
        twin_type: TwinType,
        version: int
    ) -> Optional[BaseTwinState]:
        """Get state at a specific version"""
        history = self.get_history(twin_id, twin_type, limit=1000)
        
        for record in history:
            if record.version == version:
                state_class = self._get_state_class(twin_type)
                return state_class.parse_raw(record.state_json)
        
        return None
    
    # =========================================================================
    # Event Subscriptions
    # =========================================================================
    
    def subscribe(
        self,
        event_type: Union[TwinEventType, str],
        callback: Callable[[TwinStateEvent], None],
        twin_type: Optional[TwinType] = None,
        retailer_id: Optional[str] = None
    ) -> str:
        """
        Subscribe to twin state events.
        
        Args:
            event_type: Type of event to subscribe to (or "*" for all)
            callback: Function to call when event occurs
            twin_type: Optional filter by twin type
            retailer_id: Optional filter by retailer
            
        Returns:
            Subscription ID for unsubscribe
        """
        subscription_key = self._build_subscription_key(event_type, twin_type, retailer_id)
        subscription_id = f"sub_{hashlib.md5(f'{subscription_key}_{id(callback)}'.encode()).hexdigest()[:8]}"
        
        self._subscribers[subscription_key].append(callback)
        logger.debug(f"Added subscription {subscription_id} for {subscription_key}")
        
        return subscription_id
    
    def unsubscribe(self, subscription_key: str, callback: Callable):
        """Unsubscribe from events"""
        if subscription_key in self._subscribers:
            try:
                self._subscribers[subscription_key].remove(callback)
            except ValueError:
                pass
    
    def _build_subscription_key(
        self,
        event_type: Union[TwinEventType, str],
        twin_type: Optional[TwinType],
        retailer_id: Optional[str]
    ) -> str:
        """Build subscription key for routing events"""
        parts = [str(event_type)]
        if twin_type:
            parts.append(twin_type.value)
        if retailer_id:
            parts.append(retailer_id)
        return ":".join(parts)
    
    def _emit_event(
        self,
        event_type: TwinEventType,
        state: BaseTwinState,
        metrics_delta: Dict[str, float]
    ):
        """Emit event to subscribers"""
        event = TwinStateEvent(
            event_id=f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{state.twin_id[:8]}",
            event_type=event_type.value,
            twin_id=state.twin_id,
            twin_type=state.twin_type,
            retailer_id=state.retailer_id,
            timestamp=datetime.utcnow(),
            version=state.version,
            previous_version=state.version - 1 if state.version > 1 else None,
            changed_fields=list(metrics_delta.keys()),
            metrics_delta=metrics_delta,
            state_snapshot=state.dict(),
        )
        
        # Find matching subscribers
        keys_to_check = [
            str(event_type),  # Exact event type
            "*",  # Wildcard
            f"{event_type}:{state.twin_type.value}",  # Event + twin type
            f"{event_type}:{state.twin_type.value}:{state.retailer_id}",  # Full match
        ]
        
        for key in keys_to_check:
            for callback in self._subscribers.get(key, []):
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def _get_state_path(self, twin_id: str, twin_type: TwinType) -> Path:
        """Get file path for state persistence"""
        return Path(self.config.state_dir) / twin_type.value / f"{twin_id}.json"
    
    def _get_history_path(self, twin_id: str, twin_type: TwinType) -> Path:
        """Get file path for history persistence"""
        return Path(self.config.history_dir) / twin_type.value / f"{twin_id}_history.json"
    
    def _persist_state(self, state: BaseTwinState):
        """Persist state to JSON file"""
        state_path = self._get_state_path(state.twin_id, state.twin_type)
        with open(state_path, 'w') as f:
            # Use model_dump for Pydantic v2 compatibility
            try:
                state_dict = state.model_dump(mode='json')
            except AttributeError:
                state_dict = state.dict()
            json.dump(state_dict, f, indent=2, default=str)
    
    def _persist_history_record(self, record: TwinStateHistoryRecord):
        """Persist history record"""
        history_path = self._get_history_path(record.twin_id, record.twin_type)
        
        # Load existing history
        existing = []
        if history_path.exists():
            with open(history_path) as f:
                existing = json.load(f)
        
        # Append new record
        try:
            record_dict = record.model_dump(mode='json')
        except AttributeError:
            record_dict = record.dict()
        existing.append(record_dict)
        
        # Trim if needed
        if len(existing) > self.config.max_history_per_twin:
            existing = existing[-self.config.max_history_per_twin:]
        
        # Save
        with open(history_path, 'w') as f:
            json.dump(existing, f, indent=2, default=str)
    
    def _load_states(self):
        """Load all states from disk"""
        for twin_type in TwinType:
            type_dir = Path(self.config.state_dir) / twin_type.value
            if not type_dir.exists():
                continue
            
            state_class = self._get_state_class(twin_type)
            store = self._get_state_store(twin_type)
            
            for state_file in type_dir.glob("*.json"):
                try:
                    with open(state_file) as f:
                        state_data = json.load(f)
                    state = state_class(**state_data)
                    store[state.twin_id] = state
                except Exception as e:
                    logger.error(f"Error loading state from {state_file}: {e}")
        
        total = sum(len(self._get_state_store(t)) for t in TwinType)
        logger.info(f"Loaded {total} twin states from disk")
    
    def _load_history(
        self,
        twin_id: str,
        twin_type: TwinType,
        limit: int
    ) -> List[TwinStateHistoryRecord]:
        """Load history from disk"""
        history_path = self._get_history_path(twin_id, twin_type)
        
        if not history_path.exists():
            return []
        
        try:
            with open(history_path) as f:
                records_data = json.load(f)
            
            records = [TwinStateHistoryRecord(**r) for r in records_data[-limit:]]
            return records
        except Exception as e:
            logger.error(f"Error loading history from {history_path}: {e}")
            return []
    
    def persist_all(self):
        """Persist all current states to disk"""
        count = 0
        for twin_type in TwinType:
            store = self._get_state_store(twin_type)
            for state in store.values():
                self._persist_state(state)
                count += 1
        
        logger.info(f"Persisted {count} twin states to disk")
    
    # =========================================================================
    # Metrics
    # =========================================================================
    
    def _compute_metrics_delta(
        self,
        old_state: BaseTwinState,
        new_state: BaseTwinState
    ) -> Dict[str, float]:
        """Compute delta between old and new state metrics"""
        delta = {}
        old_dict = old_state.dict()
        new_dict = new_state.dict()
        
        # Numeric fields to track
        numeric_fields = [
            'impressions', 'clicks', 'conversions', 'spend', 'revenue',
            'roas', 'ctr', 'cvr', 'cpc', 'cpa', 'budget', 'budget_utilized',
            'total_impressions', 'total_clicks', 'total_spend', 'total_revenue',
            'active_brands', 'active_campaigns', 'units_sold',
        ]
        
        for field in numeric_fields:
            if field in old_dict and field in new_dict:
                old_val = old_dict.get(field, 0) or 0
                new_val = new_dict.get(field, 0) or 0
                if old_val != new_val:
                    delta[field] = new_val - old_val
        
        return delta
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of store contents"""
        return {
            "rmn_count": len(self._rmn_states),
            "brand_count": len(self._brand_states),
            "campaign_count": len(self._campaign_states),
            "channel_count": len(self._channel_states),
            "total_states": sum([
                len(self._rmn_states),
                len(self._brand_states),
                len(self._campaign_states),
                len(self._channel_states),
            ]),
            "history_records": sum(len(h) for h in self._history.values()),
            "subscriber_count": sum(len(s) for s in self._subscribers.values()),
        }


# Singleton instance
_store_instance: Optional[TwinStateStore] = None


def get_twin_state_store(config: Optional[TwinStateStoreConfig] = None) -> TwinStateStore:
    """Get or create singleton store instance"""
    global _store_instance
    if _store_instance is None:
        _store_instance = TwinStateStore(config)
    return _store_instance


def reset_twin_state_store():
    """Reset singleton instance (for testing)"""
    global _store_instance
    _store_instance = None
