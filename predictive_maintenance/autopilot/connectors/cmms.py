"""
CMMS (Computerized Maintenance Management System) Connector

Provides work order management for autopilot runs.
"""

import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from .base import ConnectorBase, ConnectorConfig, ConnectorResponse, connector

logger = logging.getLogger(__name__)


@dataclass
class WorkOrder:
    """Work order data structure"""
    ticket_id: str
    title: str
    description: str
    priority: str  # P1, P2, P3, P4
    status: str  # open, in_progress, completed, cancelled
    
    # References
    asset_id: Optional[str] = None
    site_id: Optional[str] = None
    run_id: Optional[str] = None
    
    # Assignment
    assigned_to: Optional[str] = None
    assigned_team: Optional[str] = None
    
    # Evidence
    evidence_pack_url: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Notes
    technician_notes: str = ""
    resolution_notes: str = ""
    
    # Tags
    tags: List[str] = field(default_factory=list)


class CMSSConnector(ConnectorBase):
    """
    Abstract CMMS connector interface.
    
    Provides:
    - create_ticket(): Create a new work order
    - update_ticket(): Update an existing work order
    - get_ticket(): Retrieve work order details
    - attach_evidence(): Attach evidence pack to work order
    """
    
    @abstractmethod
    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "P2",
        asset_id: str = None,
        site_id: str = None,
        run_id: str = None,
        tags: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new work order.
        
        Args:
            title: Ticket title
            description: Detailed description
            priority: Priority level (P1-P4)
            asset_id: Related asset
            site_id: Related site
            run_id: Autopilot run ID
            tags: Classification tags
            
        Returns:
            Dict with ticket details including ticket_id
        """
        pass
    
    @abstractmethod
    def update_ticket(
        self,
        ticket_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an existing work order.
        
        Args:
            ticket_id: Ticket to update
            updates: Fields to update
            
        Returns:
            Updated ticket details
        """
        pass
    
    @abstractmethod
    def get_ticket(self, ticket_id: str) -> Optional[WorkOrder]:
        """
        Get work order details.
        
        Args:
            ticket_id: Ticket ID
            
        Returns:
            WorkOrder or None if not found
        """
        pass
    
    @abstractmethod
    def attach_evidence(
        self,
        ticket_id: str,
        evidence_pack_url: str,
        evidence_pack_id: str,
    ) -> ConnectorResponse:
        """
        Attach evidence pack to work order.
        
        Args:
            ticket_id: Ticket to attach to
            evidence_pack_url: URL to evidence pack
            evidence_pack_id: Evidence pack ID
            
        Returns:
            ConnectorResponse with attachment result
        """
        pass
    
    @abstractmethod
    def add_note(
        self,
        ticket_id: str,
        note: str,
        note_type: str = "comment",
    ) -> ConnectorResponse:
        """
        Add a note to work order.
        
        Args:
            ticket_id: Ticket ID
            note: Note content
            note_type: Type of note (comment, technician, resolution)
            
        Returns:
            ConnectorResponse with result
        """
        pass
    
    @abstractmethod
    def list_tickets(
        self,
        site_id: str = None,
        asset_id: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[WorkOrder]:
        """
        List work orders with filtering.
        
        Returns:
            List of WorkOrder objects
        """
        pass


@connector("mock_cmms")
class MockCMSSConnector(CMSSConnector):
    """
    Mock CMMS connector for development and testing.
    """
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._tickets: Dict[str, WorkOrder] = {}
        self._notes: Dict[str, List[Dict[str, Any]]] = {}
    
    def connect(self) -> bool:
        logger.info(f"[{self.name}] Mock CMMS connected")
        self._connected = True
        return True
    
    def disconnect(self) -> bool:
        logger.info(f"[{self.name}] Mock CMMS disconnected")
        self._connected = False
        return True
    
    def health_check(self) -> bool:
        return self._connected
    
    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "P2",
        asset_id: str = None,
        site_id: str = None,
        run_id: str = None,
        tags: List[str] = None,
    ) -> Dict[str, Any]:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        
        self._log_operation("create_ticket", {
            "ticket_id": ticket_id,
            "title": title,
            "priority": priority,
        })
        
        ticket = WorkOrder(
            ticket_id=ticket_id,
            title=title,
            description=description,
            priority=priority,
            status="open",
            asset_id=asset_id,
            site_id=site_id,
            run_id=run_id,
            tags=tags or [],
        )
        
        self._tickets[ticket_id] = ticket
        self._notes[ticket_id] = []
        
        return {
            "ticket_id": ticket_id,
            "title": title,
            "priority": priority,
            "status": "open",
            "created_at": ticket.created_at.isoformat(),
        }
    
    def update_ticket(
        self,
        ticket_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._log_operation("update_ticket", {
            "ticket_id": ticket_id,
            "updates": updates,
        })
        
        if ticket_id not in self._tickets:
            return {"error": "Ticket not found"}
        
        ticket = self._tickets[ticket_id]
        
        for key, value in updates.items():
            if hasattr(ticket, key):
                setattr(ticket, key, value)
        
        ticket.updated_at = datetime.utcnow()
        
        return {
            "ticket_id": ticket_id,
            "status": ticket.status,
            "updated_at": ticket.updated_at.isoformat(),
        }
    
    def get_ticket(self, ticket_id: str) -> Optional[WorkOrder]:
        return self._tickets.get(ticket_id)
    
    def attach_evidence(
        self,
        ticket_id: str,
        evidence_pack_url: str,
        evidence_pack_id: str,
    ) -> ConnectorResponse:
        self._log_operation("attach_evidence", {
            "ticket_id": ticket_id,
            "evidence_pack_id": evidence_pack_id,
        })
        
        if ticket_id not in self._tickets:
            return ConnectorResponse(
                success=False,
                error="Ticket not found",
            )
        
        ticket = self._tickets[ticket_id]
        ticket.evidence_pack_url = evidence_pack_url
        ticket.attachments.append(evidence_pack_id)
        ticket.updated_at = datetime.utcnow()
        
        return ConnectorResponse(
            success=True,
            data={
                "ticket_id": ticket_id,
                "evidence_pack_id": evidence_pack_id,
                "attached": True,
            },
        )
    
    def add_note(
        self,
        ticket_id: str,
        note: str,
        note_type: str = "comment",
    ) -> ConnectorResponse:
        self._log_operation("add_note", {
            "ticket_id": ticket_id,
            "note_type": note_type,
        })
        
        if ticket_id not in self._tickets:
            return ConnectorResponse(
                success=False,
                error="Ticket not found",
            )
        
        note_entry = {
            "note_id": str(uuid.uuid4())[:8],
            "content": note,
            "type": note_type,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        self._notes[ticket_id].append(note_entry)
        
        return ConnectorResponse(
            success=True,
            data=note_entry,
        )
    
    def list_tickets(
        self,
        site_id: str = None,
        asset_id: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[WorkOrder]:
        result = []
        
        for ticket in self._tickets.values():
            if site_id and ticket.site_id != site_id:
                continue
            if asset_id and ticket.asset_id != asset_id:
                continue
            if status and ticket.status != status:
                continue
            
            result.append(ticket)
            
            if len(result) >= limit:
                break
        
        return result
    
    def get_mock_tickets(self) -> Dict[str, WorkOrder]:
        """Get all mock tickets (for testing)"""
        return self._tickets.copy()
