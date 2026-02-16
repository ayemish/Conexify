"""
Data Connectors — load data from various sources into the platform.

Supported: CSV/XLSX upload, REST API, SFTP, cloud storage, database.
Each connector produces a standardized DataFrame-like structure
for downstream normalization.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConnectorConfig:
    """Configuration for a data connector."""
    connector_type: str  # "csv", "api", "sftp", "s3", "database"
    name: str = ""
    credentials: Dict[str, str] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    schedule: Optional[str] = None  # "once", "hourly", "daily", "weekly"
    last_run_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        safe_creds = {k: "***" for k in self.credentials}
        return {
            "connector_type": self.connector_type,
            "name": self.name,
            "credentials": safe_creds,
            "parameters": self.parameters,
            "schedule": self.schedule,
            "last_run_ts": self.last_run_ts,
        }


@dataclass
class LoadResult:
    """Result of a data load operation."""
    connector_name: str
    rows_loaded: int = 0
    rows_rejected: int = 0
    columns: List[str] = field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data: List[Dict[str, Any]] = field(default_factory=list)
    load_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connector_name": self.connector_name,
            "rows_loaded": self.rows_loaded,
            "rows_rejected": self.rows_rejected,
            "columns": self.columns,
            "sample_rows": self.sample_rows[:5],
            "errors": self.errors,
            "warnings": self.warnings,
            "load_ts": self.load_ts,
        }


class BaseConnector(ABC):
    """Base class for all data connectors."""

    def __init__(self, config: ConnectorConfig):
        self.config = config

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Test the connection. Returns (success, message)."""
        pass

    @abstractmethod
    def load(self, **kwargs) -> LoadResult:
        """Load data from the source."""
        pass

    @abstractmethod
    def preview(self, rows: int = 5) -> LoadResult:
        """Preview a sample of data without full load."""
        pass


class CSVConnector(BaseConnector):
    """Load data from CSV or XLSX files."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.file_path = config.parameters.get("file_path", "")
        self.delimiter = config.parameters.get("delimiter", ",")
        self.encoding = config.parameters.get("encoding", "utf-8")
        self.has_header = config.parameters.get("has_header", True)

    def test_connection(self) -> Tuple[bool, str]:
        if not self.file_path:
            return False, "No file path specified"
        if not Path(self.file_path).exists():
            return False, f"File not found: {self.file_path}"
        return True, "File accessible"

    def load(self, **kwargs) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)

        try:
            file_path = kwargs.get("file_path", self.file_path)
            if not file_path:
                result.errors.append("No file path")
                return result

            if file_path.endswith((".xlsx", ".xls")):
                return self._load_excel(file_path, result)

            with open(file_path, "r", encoding=self.encoding) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)
                result.columns = reader.fieldnames or []

                for i, row in enumerate(reader):
                    result.data.append(dict(row))
                    if i < 5:
                        result.sample_rows.append(dict(row))

                result.rows_loaded = len(result.data)

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"CSV load error: {e}")

        return result

    def _load_excel(self, file_path: str, result: LoadResult) -> LoadResult:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))

            if not rows:
                result.warnings.append("Empty worksheet")
                return result

            headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[0])]
            result.columns = headers

            for i, row in enumerate(rows[1:]):
                row_dict = {headers[j]: val for j, val in enumerate(row) if j < len(headers)}
                result.data.append(row_dict)
                if i < 5:
                    result.sample_rows.append(row_dict)

            result.rows_loaded = len(result.data)
            wb.close()
        except ImportError:
            result.errors.append("openpyxl not installed for Excel support")
        except Exception as e:
            result.errors.append(f"Excel load error: {e}")

        return result

    def preview(self, rows: int = 5) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)
        try:
            with open(self.file_path, "r", encoding=self.encoding) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)
                result.columns = reader.fieldnames or []
                for i, row in enumerate(reader):
                    if i >= rows:
                        break
                    result.sample_rows.append(dict(row))
                    result.data.append(dict(row))
                result.rows_loaded = len(result.data)
        except Exception as e:
            result.errors.append(str(e))
        return result

    def load_from_string(self, csv_content: str) -> LoadResult:
        """Load CSV data from a string (for upload scenarios)."""
        result = LoadResult(connector_name=self.config.name)
        try:
            reader = csv.DictReader(io.StringIO(csv_content), delimiter=self.delimiter)
            result.columns = reader.fieldnames or []
            for i, row in enumerate(reader):
                result.data.append(dict(row))
                if i < 5:
                    result.sample_rows.append(dict(row))
            result.rows_loaded = len(result.data)
        except Exception as e:
            result.errors.append(str(e))
        return result


class APIConnector(BaseConnector):
    """Load data from REST/GraphQL APIs."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.base_url = config.parameters.get("base_url", "")
        self.auth_type = config.parameters.get("auth_type", "bearer")
        self.headers = config.parameters.get("headers", {})
        self.pagination = config.parameters.get("pagination", {})

    def test_connection(self) -> Tuple[bool, str]:
        if not self.base_url:
            return False, "No base URL specified"
        try:
            import requests
            headers = self._build_headers()
            resp = requests.get(self.base_url, headers=headers, timeout=10)
            if resp.status_code < 400:
                return True, f"Connected (HTTP {resp.status_code})"
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except ImportError:
            return False, "requests library not installed"
        except Exception as e:
            return False, str(e)

    def _build_headers(self) -> Dict[str, str]:
        headers = dict(self.headers)
        token = self.config.credentials.get("token", "")
        if self.auth_type == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "api_key":
            key_header = self.config.parameters.get("api_key_header", "X-API-Key")
            headers[key_header] = self.config.credentials.get("api_key", "")
        return headers

    def load(self, **kwargs) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)
        try:
            import requests
            endpoint = kwargs.get("endpoint", self.base_url)
            params = kwargs.get("params", {})
            headers = self._build_headers()

            resp = requests.get(endpoint, headers=headers, params=params, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            if isinstance(data, list):
                result.data = data
            elif isinstance(data, dict):
                # Look for common data keys
                for key in ("data", "results", "items", "records"):
                    if key in data and isinstance(data[key], list):
                        result.data = data[key]
                        break
                if not result.data:
                    result.data = [data]

            result.rows_loaded = len(result.data)
            if result.data:
                result.columns = list(result.data[0].keys())
                result.sample_rows = result.data[:5]

        except ImportError:
            result.errors.append("requests library not installed")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def preview(self, rows: int = 5) -> LoadResult:
        return self.load(params={"limit": rows})


class DatabaseConnector(BaseConnector):
    """Load data from database read replicas."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.connection_string = config.parameters.get("connection_string", "")
        self.query = config.parameters.get("query", "")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.connection_string:
            return False, "No connection string specified"
        # Actual connection test would use sqlalchemy
        return True, "Connection string provided (test requires sqlalchemy)"

    def load(self, **kwargs) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)
        query = kwargs.get("query", self.query)

        if not query:
            result.errors.append("No query specified")
            return result

        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(self.connection_string)
            with engine.connect() as conn:
                rows = conn.execute(text(query))
                result.columns = list(rows.keys())
                for i, row in enumerate(rows):
                    row_dict = dict(zip(result.columns, row))
                    result.data.append(row_dict)
                    if i < 5:
                        result.sample_rows.append(row_dict)
                result.rows_loaded = len(result.data)
        except ImportError:
            result.errors.append("sqlalchemy not installed")
        except Exception as e:
            result.errors.append(str(e))

        return result

    def preview(self, rows: int = 5) -> LoadResult:
        return self.load(query=f"{self.query} LIMIT {rows}" if self.query else "")


class SFTPConnector(BaseConnector):
    """Load data from SFTP servers."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.host = config.parameters.get("host", "")
        self.port = int(config.parameters.get("port", 22))
        self.remote_path = config.parameters.get("remote_path", "")
        self.username = config.credentials.get("username", "")
        self.password = config.credentials.get("password")
        self.key_path = config.credentials.get("key_path")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.host:
            return False, "No host specified"
        try:
            import paramiko
            transport = paramiko.Transport((self.host, self.port))
            if self.key_path:
                key = paramiko.RSAKey.from_private_key_file(self.key_path)
                transport.connect(username=self.username, pkey=key)
            else:
                transport.connect(username=self.username, password=self.password)
            transport.close()
            return True, "SFTP connection successful"
        except ImportError:
            return False, "paramiko not installed"
        except Exception as e:
            return False, str(e)

    def load(self, **kwargs) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)
        try:
            import paramiko
            transport = paramiko.Transport((self.host, self.port))
            if self.key_path:
                key = paramiko.RSAKey.from_private_key_file(self.key_path)
                transport.connect(username=self.username, pkey=key)
            else:
                transport.connect(username=self.username, password=self.password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            remote = kwargs.get("remote_path", self.remote_path)
            with sftp.open(remote, "r") as f:
                content = f.read().decode("utf-8")
            sftp.close()
            transport.close()
            csv_conn = CSVConnector(self.config)
            return csv_conn.load_from_string(content)
        except ImportError:
            result.errors.append("paramiko not installed")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def preview(self, rows: int = 5) -> LoadResult:
        full = self.load()
        full.data = full.data[:rows]
        full.rows_loaded = len(full.data)
        return full


class S3Connector(BaseConnector):
    """Load data from Amazon S3 or compatible object stores."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.bucket = config.parameters.get("bucket", "")
        self.key = config.parameters.get("key", "")
        self.region = config.parameters.get("region", "us-east-1")
        self.endpoint_url = config.parameters.get("endpoint_url")

    def _get_client(self):
        import boto3
        kwargs = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        ak = self.config.credentials.get("aws_access_key_id")
        sk = self.config.credentials.get("aws_secret_access_key")
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
        return boto3.client("s3", **kwargs)

    def test_connection(self) -> Tuple[bool, str]:
        if not self.bucket:
            return False, "No bucket specified"
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket)
            return True, "S3 bucket accessible"
        except ImportError:
            return False, "boto3 not installed"
        except Exception as e:
            return False, str(e)

    def load(self, **kwargs) -> LoadResult:
        result = LoadResult(connector_name=self.config.name)
        try:
            client = self._get_client()
            obj_key = kwargs.get("key", self.key)
            response = client.get_object(Bucket=self.bucket, Key=obj_key)
            content = response["Body"].read().decode("utf-8")
            csv_conn = CSVConnector(self.config)
            return csv_conn.load_from_string(content)
        except ImportError:
            result.errors.append("boto3 not installed")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def preview(self, rows: int = 5) -> LoadResult:
        full = self.load()
        full.data = full.data[:rows]
        full.rows_loaded = len(full.data)
        return full


class ConnectorFactory:
    """Factory for creating data connectors from configuration."""

    _REGISTRY = {
        "csv": CSVConnector,
        "xlsx": CSVConnector,
        "api": APIConnector,
        "database": DatabaseConnector,
        "sftp": SFTPConnector,
        "s3": S3Connector,
    }

    @classmethod
    def create(cls, config: ConnectorConfig) -> BaseConnector:
        connector_cls = cls._REGISTRY.get(config.connector_type)
        if not connector_cls:
            raise ValueError(f"Unknown connector type: {config.connector_type}")
        return connector_cls(config)

    @classmethod
    def available_types(cls) -> List[str]:
        return list(cls._REGISTRY.keys())
