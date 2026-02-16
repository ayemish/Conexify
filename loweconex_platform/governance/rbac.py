"""
Role-Based Access Control (RBAC) for the Loweconex platform.

Provides tenant isolation (company boundary), role permissions,
and user management aligned with FRD Section 2.2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Granular permissions for platform operations."""
    # Report
    REPORT_READ = "report:read"
    REPORT_EXPORT = "report:export"

    # Scenarios
    SCENARIO_RUN = "scenario:run"
    SCENARIO_CREATE = "scenario:create"

    # Data
    DATA_CONNECT = "data:connect"
    DATA_MAP_SCHEMA = "data:map_schema"
    DATA_IMPORT = "data:import"

    # Agents / System
    AGENT_MANAGE = "agent:manage"
    THRESHOLD_MANAGE = "threshold:manage"
    MODEL_MANAGE = "model:manage"

    # Admin
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"
    TENANT_MANAGE = "tenant:manage"


class Role(Enum):
    """Pre-defined roles per FRD Section 2.2."""
    READ_ONLY = "read_only"
    ANALYST = "analyst"
    DATA_ADMIN = "data_admin"
    SYSTEM_ADMIN = "system_admin"


# Role -> Permission mapping
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.READ_ONLY: {
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
    },
    Role.ANALYST: {
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.SCENARIO_RUN,
        Permission.SCENARIO_CREATE,
    },
    Role.DATA_ADMIN: {
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.SCENARIO_RUN,
        Permission.SCENARIO_CREATE,
        Permission.DATA_CONNECT,
        Permission.DATA_MAP_SCHEMA,
        Permission.DATA_IMPORT,
        Permission.AUDIT_READ,
    },
    Role.SYSTEM_ADMIN: set(Permission),  # All permissions
}


@dataclass
class User:
    """A platform user with tenant and role assignments."""
    user_id: str
    email: str
    display_name: str
    company_id: str  # Tenant boundary
    roles: List[Role] = field(default_factory=list)
    active: bool = True

    @property
    def permissions(self) -> Set[Permission]:
        perms: Set[Permission] = set()
        for role in self.roles:
            perms.update(ROLE_PERMISSIONS.get(role, set()))
        return perms

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "company_id": self.company_id,
            "roles": [r.value for r in self.roles],
            "permissions": [p.value for p in self.permissions],
            "active": self.active,
        }


class RBACManager:
    """
    Manages users, roles, and permission checks with hard tenant isolation.
    
    All operations are scoped to a company_id boundary.
    Cross-tenant access is never permitted.
    """

    def __init__(self):
        self._users: Dict[str, User] = {}

    def add_user(self, user: User) -> User:
        self._users[user.user_id] = user
        logger.info(f"User added: {user.user_id} ({user.email}) for company {user.company_id}")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def check_access(
        self,
        user_id: str,
        company_id: str,
        permission: Permission,
    ) -> bool:
        """
        Check if a user has the given permission within the given company.
        
        Enforces hard tenant isolation: user's company_id must match.
        """
        user = self._users.get(user_id)
        if not user:
            logger.warning(f"Access denied: unknown user {user_id}")
            return False
        if not user.active:
            logger.warning(f"Access denied: inactive user {user_id}")
            return False
        if user.company_id != company_id:
            logger.warning(f"Access denied: tenant boundary violation for user {user_id}")
            return False
        if not user.has_permission(permission):
            logger.warning(f"Access denied: {user_id} lacks {permission.value}")
            return False
        return True

    def assign_role(self, user_id: str, role: Role) -> bool:
        user = self._users.get(user_id)
        if not user:
            return False
        if role not in user.roles:
            user.roles.append(role)
        return True

    def remove_role(self, user_id: str, role: Role) -> bool:
        user = self._users.get(user_id)
        if not user:
            return False
        if role in user.roles:
            user.roles.remove(role)
        return True

    def list_users_by_company(self, company_id: str) -> List[User]:
        return [u for u in self._users.values() if u.company_id == company_id]
