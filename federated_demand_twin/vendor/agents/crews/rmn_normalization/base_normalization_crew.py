"""
Base Normalization Crew

Abstract base class for retailer-specific RMN normalization crews.
Defines the canonical schema and common normalization patterns.
"""

from abc import ABC, abstractmethod
from crewai import Agent, Task, Crew
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CampaignObjective(str, Enum):
    """Canonical campaign objectives"""
    BRAND_AWARENESS = "brand_awareness"
    CONSIDERATION = "consideration"
    CONVERSION = "conversion"
    LOYALTY = "loyalty"


class AdFormat(str, Enum):
    """Canonical ad formats"""
    SPONSORED_PRODUCT = "sponsored_product"
    SPONSORED_BRAND = "sponsored_brand"
    SPONSORED_VIDEO = "sponsored_video"
    DISPLAY = "display"
    NATIVE = "native"
    SEARCH = "search"
    IN_STORE = "in_store"


class AttributionModel(str, Enum):
    """Canonical attribution models"""
    LAST_CLICK = "last_click"
    FIRST_CLICK = "first_click"
    LINEAR = "linear"
    TIME_DECAY = "time_decay"
    POSITION_BASED = "position_based"
    DATA_DRIVEN = "data_driven"


@dataclass
class CanonicalCampaign:
    """Canonical campaign structure"""
    campaign_id: str
    retailer_id: str
    campaign_name: str
    advertiser_id: str
    objective: CampaignObjective
    budget: float
    daily_budget: Optional[float]
    start_date: datetime
    end_date: Optional[datetime]
    status: str
    ad_format: AdFormat
    targeting: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalPerformance:
    """Canonical performance metrics"""
    date: datetime
    campaign_id: str
    retailer_id: str
    impressions: int
    clicks: int
    spend: float
    conversions: int
    revenue: float
    units_sold: int
    new_to_brand: int
    roas: float
    ctr: float
    cpc: float
    cvr: float
    attribution_window: int  # days
    attribution_model: AttributionModel


@dataclass
class CanonicalProduct:
    """Canonical product mapping"""
    product_id: str
    retailer_id: str
    retailer_sku: str
    upc: str
    product_name: str
    brand: str
    category: str
    subcategory: str
    price: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNormalizationCrew(ABC):
    """
    Abstract base class for RMN normalization crews.
    
    Each retailer-specific crew must implement:
    - Schema discovery
    - Attribution mapping
    - Taxonomy translation
    - Data validation
    """
    
    def __init__(self, retailer_id: str, retailer_name: str, event_bus=None):
        self.retailer_id = retailer_id
        self.retailer_name = retailer_name
        self.event_bus = event_bus
        
        # Create agents
        self.schema_discovery_agent = self._create_schema_discovery_agent()
        self.attribution_mapper_agent = self._create_attribution_mapper_agent()
        self.taxonomy_translator_agent = self._create_taxonomy_translator_agent()
        self.data_validator_agent = self._create_data_validator_agent()
        
        # Create crew
        self.crew = self._create_crew()
    
    def _create_schema_discovery_agent(self) -> Agent:
        """Create the schema discovery agent"""
        return Agent(
            role=f"{self.retailer_name} Schema Discovery Agent",
            goal=f"Discover and document all schema elements from {self.retailer_name}'s retail media API",
            backstory=f"""You are an expert in {self.retailer_name}'s retail media API.
            Your job is to discover all available data schemas, understand their structure,
            and document the relationships between different data entities.""",
            verbose=True,
            allow_delegation=False
        )
    
    def _create_attribution_mapper_agent(self) -> Agent:
        """Create the attribution mapper agent"""
        return Agent(
            role=f"{self.retailer_name} Attribution Mapper",
            goal=f"Map {self.retailer_name}'s attribution model and windows to canonical format",
            backstory=f"""You are an expert in retail media attribution.
            Your job is to understand {self.retailer_name}'s specific attribution model
            and map it to the canonical attribution format used across all retailers.""",
            verbose=True,
            allow_delegation=False
        )
    
    def _create_taxonomy_translator_agent(self) -> Agent:
        """Create the taxonomy translator agent"""
        return Agent(
            role=f"{self.retailer_name} Taxonomy Translator",
            goal=f"Translate {self.retailer_name}'s product and category taxonomy to canonical format",
            backstory=f"""You are an expert in product taxonomy and categorization.
            Your job is to map {self.retailer_name}'s specific category hierarchy
            and product attributes to the canonical taxonomy.""",
            verbose=True,
            allow_delegation=False
        )
    
    def _create_data_validator_agent(self) -> Agent:
        """Create the data validator agent"""
        return Agent(
            role=f"{self.retailer_name} Data Validator",
            goal="Validate normalized data against canonical schema and business rules",
            backstory="""You are an expert in data quality and validation.
            Your job is to ensure all normalized data conforms to the canonical schema
            and passes all business validation rules.""",
            verbose=True,
            allow_delegation=False
        )
    
    def _create_crew(self) -> Crew:
        """Create the normalization crew"""
        return Crew(
            agents=[
                self.schema_discovery_agent,
                self.attribution_mapper_agent,
                self.taxonomy_translator_agent,
                self.data_validator_agent
            ],
            tasks=[],  # Tasks added dynamically
            verbose=True
        )
    
    @abstractmethod
    def get_retailer_schema(self) -> Dict[str, Any]:
        """Get the retailer-specific schema definition"""
        pass
    
    @abstractmethod
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        """Map a retailer campaign to canonical format"""
        pass
    
    @abstractmethod
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        """Map retailer performance metrics to canonical format"""
        pass
    
    @abstractmethod
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        """Map a retailer product to canonical format"""
        pass
    
    @abstractmethod
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        """Get mapping from retailer attribution types to canonical"""
        pass
    
    @abstractmethod
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        """Get mapping from retailer categories to canonical"""
        pass
    
    def normalize_batch(
        self,
        campaigns: List[Dict[str, Any]],
        performance: List[Dict[str, Any]],
        products: List[Dict[str, Any]]
    ) -> Dict[str, List[Any]]:
        """Normalize a batch of retailer data"""
        results = {
            "campaigns": [],
            "performance": [],
            "products": [],
            "errors": []
        }
        
        # Normalize campaigns
        for campaign in campaigns:
            try:
                canonical = self.map_campaign(campaign)
                results["campaigns"].append(canonical)
            except Exception as e:
                results["errors"].append({
                    "type": "campaign",
                    "data": campaign,
                    "error": str(e)
                })
        
        # Normalize performance
        for perf in performance:
            try:
                canonical = self.map_performance(perf)
                results["performance"].append(canonical)
            except Exception as e:
                results["errors"].append({
                    "type": "performance",
                    "data": perf,
                    "error": str(e)
                })
        
        # Normalize products
        for product in products:
            try:
                canonical = self.map_product(product)
                results["products"].append(canonical)
            except Exception as e:
                results["errors"].append({
                    "type": "product",
                    "data": product,
                    "error": str(e)
                })
        
        self._emit_event("data.normalized", {
            "retailer_id": self.retailer_id,
            "campaigns_normalized": len(results["campaigns"]),
            "performance_normalized": len(results["performance"]),
            "products_normalized": len(results["products"]),
            "errors": len(results["errors"])
        })
        
        return results
    
    def validate_canonical(self, data: Any, data_type: str) -> Dict[str, Any]:
        """Validate normalized data against canonical schema"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        if data_type == "campaign":
            if not isinstance(data, CanonicalCampaign):
                validation_result["valid"] = False
                validation_result["errors"].append("Not a CanonicalCampaign instance")
            elif not data.campaign_id:
                validation_result["valid"] = False
                validation_result["errors"].append("Missing campaign_id")
            elif data.budget <= 0:
                validation_result["warnings"].append("Budget is zero or negative")
        
        elif data_type == "performance":
            if not isinstance(data, CanonicalPerformance):
                validation_result["valid"] = False
                validation_result["errors"].append("Not a CanonicalPerformance instance")
            elif data.impressions < 0:
                validation_result["valid"] = False
                validation_result["errors"].append("Negative impressions")
            elif data.spend < 0:
                validation_result["valid"] = False
                validation_result["errors"].append("Negative spend")
        
        return validation_result
    
    def create_normalization_tasks(self) -> List[Task]:
        """Create tasks for the normalization workflow"""
        return [
            Task(
                description=f"""Discover the {self.retailer_name} retail media API schema.
                
                Steps:
                1. Document all available endpoints
                2. Identify campaign, performance, and product schemas
                3. Document field types and relationships
                4. Identify any retailer-specific fields
                """,
                expected_output="Complete schema documentation with field mappings",
                agent=self.schema_discovery_agent
            ),
            Task(
                description=f"""Map {self.retailer_name}'s attribution model to canonical format.
                
                Steps:
                1. Identify attribution windows used
                2. Map attribution types to canonical models
                3. Document any limitations or differences
                4. Create transformation rules
                """,
                expected_output="Attribution mapping documentation with transformation rules",
                agent=self.attribution_mapper_agent
            ),
            Task(
                description=f"""Translate {self.retailer_name}'s taxonomy to canonical format.
                
                Steps:
                1. Map product categories to canonical taxonomy
                2. Translate ad format types
                3. Normalize targeting segment names
                4. Create category crosswalk table
                """,
                expected_output="Complete taxonomy mapping with crosswalk tables",
                agent=self.taxonomy_translator_agent
            ),
            Task(
                description="""Validate the normalized data against canonical schema.
                
                Steps:
                1. Check all required fields are present
                2. Validate data types and formats
                3. Verify business rule compliance
                4. Generate validation report
                """,
                expected_output="Validation report with any errors or warnings",
                agent=self.data_validator_agent
            )
        ]
    
    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Emit an event to the message bus"""
        if self.event_bus:
            self.event_bus.send_agent_event(
                event_type=event_type,
                agent_id=f"{self.retailer_id}_normalization",
                payload=payload
            )
