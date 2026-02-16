"""
ServiceNow CMMS Connector

Production-ready connector for ServiceNow incident and work order management.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid
import json

import httpx

from .base import ConnectorConfig, ConnectorResponse, connector
from .cmms import CMSSConnector, WorkOrder

logger = logging.getLogger(__name__)


@dataclass
class ServiceNowConfig(ConnectorConfig):
    """ServiceNow-specific configuration"""
    instance_url: str = ""
    username: str = ""
    password: str = ""
    client_id: str = ""
    client_secret: str = ""
    use_oauth: bool = False
    table_name: str = "incident"
    assignment_group: str = ""
    caller_id: str = ""
    category: str = "HVAC"
    subcategory: str = "Predictive Maintenance"
    timeout_seconds: int = 30


PRIORITY_MAP = {
    "P1": "1",
    "P2": "2", 
    "P3": "3",
    "P4": "4",
}

STATUS_MAP = {
    "1": "open",
    "2": "in_progress",
    "3": "on_hold",
    "6": "resolved",
    "7": "closed",
    "8": "cancelled",
}

REVERSE_STATUS_MAP = {v: k for k, v in STATUS_MAP.items()}


@connector("servicenow")
class ServiceNowConnector(CMSSConnector):
    """
    ServiceNow CMMS connector for incident and work order management.
    
    Supports:
    - Basic auth and OAuth 2.0 authentication
    - Incident creation with full PDM context
    - Work order attachment and notes
    - Bidirectional status sync
    """
    
    def __init__(self, config: ServiceNowConfig):
        super().__init__(config)
        self.config: ServiceNowConfig = config
        self._client: Optional[httpx.Client] = None
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
    
    def connect(self) -> bool:
        """Establish connection to ServiceNow instance"""
        try:
            self._client = httpx.Client(
                base_url=self.config.instance_url.rstrip('/'),
                timeout=self.config.timeout_seconds,
            )
            
            if self.config.use_oauth:
                self._authenticate_oauth()
            else:
                self._client.auth = (self.config.username, self.config.password)
            
            if self.health_check():
                self._connected = True
                logger.info(f"[{self.name}] Connected to ServiceNow: {self.config.instance_url}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[{self.name}] ServiceNow connection failed: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Close ServiceNow connection"""
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False
        self._access_token = None
        logger.info(f"[{self.name}] Disconnected from ServiceNow")
        return True
    
    def health_check(self) -> bool:
        """Verify ServiceNow connectivity"""
        try:
            response = self._request("GET", "/api/now/table/sys_user?sysparm_limit=1")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"[{self.name}] Health check failed: {e}")
            return False
    
    def _authenticate_oauth(self):
        """Authenticate using OAuth 2.0"""
        token_url = f"{self.config.instance_url}/oauth_token.do"
        
        response = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "username": self.config.username,
                "password": self.config.password,
            },
        )
        
        if response.status_code == 200:
            data = response.json()
            self._access_token = data["access_token"]
            expires_in = int(data.get("expires_in", 3600))
            self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in - 60)
        else:
            raise Exception(f"OAuth authentication failed: {response.text}")
    
    def _request(
        self,
        method: str,
        path: str,
        data: Dict[str, Any] = None,
    ) -> httpx.Response:
        """Make authenticated request to ServiceNow API"""
        if not self._client:
            raise Exception("Not connected to ServiceNow")
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        if self.config.use_oauth:
            if self._token_expires and datetime.utcnow() >= self._token_expires:
                self._authenticate_oauth()
            headers["Authorization"] = f"Bearer {self._access_token}"
        
        if method == "GET":
            return self._client.get(path, headers=headers)
        elif method == "POST":
            return self._client.post(path, headers=headers, json=data)
        elif method == "PUT":
            return self._client.put(path, headers=headers, json=data)
        elif method == "PATCH":
            return self._client.patch(path, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
    
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
        """Create a new ServiceNow incident"""
        self._log_operation("create_ticket", {
            "title": title,
            "priority": priority,
            "asset_id": asset_id,
        })
        
        payload = {
            "short_description": title,
            "description": description,
            "priority": PRIORITY_MAP.get(priority, "2"),
            "category": self.config.category,
            "subcategory": self.config.subcategory,
            "cmdb_ci": asset_id,
            "assignment_group": self.config.assignment_group,
        }
        
        if self.config.caller_id:
            payload["caller_id"] = self.config.caller_id
        
        if run_id:
            payload["correlation_id"] = run_id
        
        if tags:
            payload["u_tags"] = ",".join(tags)
        
        payload = {k: v for k, v in payload.items() if v}
        
        try:
            response = self._request(
                "POST",
                f"/api/now/table/{self.config.table_name}",
                data=payload,
            )
            
            if response.status_code in (200, 201):
                result = response.json().get("result", {})
                ticket_id = result.get("number") or result.get("sys_id")
                
                logger.info(f"[{self.name}] Created ticket: {ticket_id}")
                
                return {
                    "ticket_id": ticket_id,
                    "sys_id": result.get("sys_id"),
                    "title": title,
                    "priority": priority,
                    "status": "open",
                    "created_at": result.get("sys_created_on"),
                    "url": f"{self.config.instance_url}/nav_to.do?uri={self.config.table_name}.do?sys_id={result.get('sys_id')}",
                }
            else:
                logger.error(f"[{self.name}] Failed to create ticket: {response.text}")
                return {"error": response.text}
                
        except Exception as e:
            logger.error(f"[{self.name}] Create ticket error: {e}")
            return {"error": str(e)}
    
    def update_ticket(
        self,
        ticket_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing ServiceNow incident"""
        self._log_operation("update_ticket", {
            "ticket_id": ticket_id,
            "updates": list(updates.keys()),
        })
        
        sys_id = self._resolve_sys_id(ticket_id)
        if not sys_id:
            return {"error": f"Ticket not found: {ticket_id}"}
        
        payload = {}
        
        if "status" in updates:
            payload["state"] = REVERSE_STATUS_MAP.get(updates["status"], updates["status"])
        if "priority" in updates:
            payload["priority"] = PRIORITY_MAP.get(updates["priority"], updates["priority"])
        if "assigned_to" in updates:
            payload["assigned_to"] = updates["assigned_to"]
        if "resolution_notes" in updates:
            payload["close_notes"] = updates["resolution_notes"]
        if "work_notes" in updates:
            payload["work_notes"] = updates["work_notes"]
        
        try:
            response = self._request(
                "PATCH",
                f"/api/now/table/{self.config.table_name}/{sys_id}",
                data=payload,
            )
            
            if response.status_code == 200:
                result = response.json().get("result", {})
                return {
                    "ticket_id": ticket_id,
                    "status": STATUS_MAP.get(result.get("state"), result.get("state")),
                    "updated_at": result.get("sys_updated_on"),
                }
            else:
                return {"error": response.text}
                
        except Exception as e:
            logger.error(f"[{self.name}] Update ticket error: {e}")
            return {"error": str(e)}
    
    def get_ticket(self, ticket_id: str) -> Optional[WorkOrder]:
        """Get ServiceNow incident details"""
        sys_id = self._resolve_sys_id(ticket_id)
        if not sys_id:
            return None
        
        try:
            response = self._request(
                "GET",
                f"/api/now/table/{self.config.table_name}/{sys_id}",
            )
            
            if response.status_code == 200:
                result = response.json().get("result", {})
                return WorkOrder(
                    ticket_id=result.get("number", ticket_id),
                    title=result.get("short_description", ""),
                    description=result.get("description", ""),
                    priority=self._reverse_priority(result.get("priority")),
                    status=STATUS_MAP.get(result.get("state"), "open"),
                    asset_id=result.get("cmdb_ci"),
                    assigned_to=result.get("assigned_to"),
                    created_at=self._parse_datetime(result.get("sys_created_on")),
                    updated_at=self._parse_datetime(result.get("sys_updated_on")),
                    resolution_notes=result.get("close_notes", ""),
                )
            
            return None
            
        except Exception as e:
            logger.error(f"[{self.name}] Get ticket error: {e}")
            return None
    
    def attach_evidence(
        self,
        ticket_id: str,
        evidence_pack_url: str,
        evidence_pack_id: str,
    ) -> ConnectorResponse:
        """Attach evidence pack URL as a work note"""
        self._log_operation("attach_evidence", {
            "ticket_id": ticket_id,
            "evidence_pack_id": evidence_pack_id,
        })
        
        note = f"""
[PDM Autopilot Evidence Pack]

Evidence Pack ID: {evidence_pack_id}
Evidence URL: {evidence_pack_url}

This evidence pack contains diagnostic data, telemetry snapshots, 
and fault analysis supporting this maintenance action.
"""
        
        return self.add_note(ticket_id, note, "work_notes")
    
    def add_note(
        self,
        ticket_id: str,
        note: str,
        note_type: str = "work_notes",
    ) -> ConnectorResponse:
        """Add a note to the ServiceNow incident"""
        sys_id = self._resolve_sys_id(ticket_id)
        if not sys_id:
            return ConnectorResponse(success=False, error="Ticket not found")
        
        field_name = "work_notes" if note_type == "work_notes" else "comments"
        
        try:
            response = self._request(
                "PATCH",
                f"/api/now/table/{self.config.table_name}/{sys_id}",
                data={field_name: note},
            )
            
            if response.status_code == 200:
                return ConnectorResponse(
                    success=True,
                    data={"ticket_id": ticket_id, "note_added": True},
                )
            else:
                return ConnectorResponse(success=False, error=response.text)
                
        except Exception as e:
            return ConnectorResponse(success=False, error=str(e))
    
    def list_tickets(
        self,
        site_id: str = None,
        asset_id: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[WorkOrder]:
        """List ServiceNow incidents with filtering"""
        query_parts = []
        
        if asset_id:
            query_parts.append(f"cmdb_ci={asset_id}")
        if status:
            state = REVERSE_STATUS_MAP.get(status, status)
            query_parts.append(f"state={state}")
        
        query = "^".join(query_parts) if query_parts else ""
        
        try:
            params = f"sysparm_limit={limit}"
            if query:
                params += f"&sysparm_query={query}"
            
            response = self._request(
                "GET",
                f"/api/now/table/{self.config.table_name}?{params}",
            )
            
            if response.status_code == 200:
                results = response.json().get("result", [])
                return [
                    WorkOrder(
                        ticket_id=r.get("number"),
                        title=r.get("short_description", ""),
                        description=r.get("description", ""),
                        priority=self._reverse_priority(r.get("priority")),
                        status=STATUS_MAP.get(r.get("state"), "open"),
                        asset_id=r.get("cmdb_ci"),
                        assigned_to=r.get("assigned_to"),
                        created_at=self._parse_datetime(r.get("sys_created_on")),
                    )
                    for r in results
                ]
            
            return []
            
        except Exception as e:
            logger.error(f"[{self.name}] List tickets error: {e}")
            return []
    
    def _resolve_sys_id(self, ticket_id: str) -> Optional[str]:
        """Resolve ticket number to sys_id"""
        if len(ticket_id) == 32:
            return ticket_id
        
        try:
            response = self._request(
                "GET",
                f"/api/now/table/{self.config.table_name}?sysparm_query=number={ticket_id}&sysparm_limit=1",
            )
            
            if response.status_code == 200:
                results = response.json().get("result", [])
                if results:
                    return results[0].get("sys_id")
            
            return None
            
        except Exception:
            return None
    
    def _reverse_priority(self, priority: str) -> str:
        """Convert ServiceNow priority to P1-P4 format"""
        reverse_map = {v: k for k, v in PRIORITY_MAP.items()}
        return reverse_map.get(str(priority), "P2")
    
    def _parse_datetime(self, dt_str: str) -> datetime:
        """Parse ServiceNow datetime string"""
        if not dt_str:
            return datetime.utcnow()
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.utcnow()
