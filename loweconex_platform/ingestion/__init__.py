"""
Data Ingestion — connectors, normalization, identity resolution,
and validation for loading data into the digital twin store.

Supports: API, SFTP, cloud storage, database, CSV/XLSX upload.
"""

from loweconex_platform.ingestion.connectors import (
    BaseConnector,
    CSVConnector,
    APIConnector,
    ConnectorFactory,
)
from loweconex_platform.ingestion.normalizer import (
    Normalizer,
    SchemaMapping,
    IdentityResolver,
)
from loweconex_platform.ingestion.validators import (
    DataValidator,
    ValidationResult,
)

__all__ = [
    "BaseConnector",
    "CSVConnector",
    "APIConnector",
    "ConnectorFactory",
    "Normalizer",
    "SchemaMapping",
    "IdentityResolver",
    "DataValidator",
    "ValidationResult",
]
