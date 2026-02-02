"""
Instacart Ads Normalization Crew

Normalizes Instacart Advertising data to canonical schema.
"""

from typing import Dict, List, Any
from datetime import datetime
from .base_normalization_crew import (
    BaseNormalizationCrew,
    CanonicalCampaign,
    CanonicalPerformance,
    CanonicalProduct,
    CampaignObjective,
    AdFormat,
    AttributionModel
)


class InstacartNormalizationCrew(BaseNormalizationCrew):
    """Instacart Ads Normalization Crew"""
    
    INSTACART_AD_FORMATS = {
        "featured_product": AdFormat.SPONSORED_PRODUCT,
        "display": AdFormat.DISPLAY,
        "search": AdFormat.SEARCH,
    }
    
    DEFAULT_ATTRIBUTION_WINDOW = 7
    
    def __init__(self, event_bus=None):
        super().__init__(
            retailer_id="instacart",
            retailer_name="Instacart",
            event_bus=event_bus
        )
    
    def get_retailer_schema(self) -> Dict[str, Any]:
        return {
            "retailer": "instacart",
            "api_version": "v1",
            "campaign_schema": {
                "campaign_id": {"type": "string", "canonical": "campaign_id"},
                "name": {"type": "string", "canonical": "campaign_name"},
                "ad_type": {"type": "string", "canonical": "ad_format"},
                "status": {"type": "string", "canonical": "status"},
                "budget": {"type": "float", "canonical": "budget"},
                "start_date": {"type": "date", "canonical": "start_date"},
                "end_date": {"type": "date", "canonical": "end_date"},
            }
        }
    
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        ad_format = self.INSTACART_AD_FORMATS.get(
            retailer_campaign.get("ad_type", "featured_product"), AdFormat.SPONSORED_PRODUCT
        )
        
        return CanonicalCampaign(
            campaign_id=str(retailer_campaign.get("campaign_id")),
            retailer_id="instacart",
            campaign_name=retailer_campaign.get("name", ""),
            advertiser_id=str(retailer_campaign.get("brand_id", "")),
            objective=CampaignObjective.CONVERSION,
            budget=retailer_campaign.get("budget", 0),
            daily_budget=retailer_campaign.get("daily_budget"),
            start_date=self._parse_date(retailer_campaign.get("start_date")),
            end_date=self._parse_date(retailer_campaign.get("end_date")),
            status=retailer_campaign.get("status", "active"),
            ad_format=ad_format,
            targeting=retailer_campaign.get("targeting", {}),
            metadata={"source": "instacart_ads"}
        )
    
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        impressions = retailer_performance.get("impressions", 0)
        clicks = retailer_performance.get("clicks", 0)
        spend = retailer_performance.get("spend", 0.0)
        revenue = retailer_performance.get("attributed_sales", 0.0)
        conversions = retailer_performance.get("orders", 0)
        
        return CanonicalPerformance(
            date=self._parse_date(retailer_performance.get("date")),
            campaign_id=str(retailer_performance.get("campaign_id")),
            retailer_id="instacart",
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=conversions,
            revenue=revenue,
            units_sold=retailer_performance.get("units", 0),
            new_to_brand=retailer_performance.get("new_customers", 0),
            roas=revenue / spend if spend > 0 else 0,
            ctr=clicks / impressions if impressions > 0 else 0,
            cpc=spend / clicks if clicks > 0 else 0,
            cvr=conversions / clicks if clicks > 0 else 0,
            attribution_window=self.DEFAULT_ATTRIBUTION_WINDOW,
            attribution_model=AttributionModel.LAST_CLICK
        )
    
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        return CanonicalProduct(
            product_id=f"instacart_{retailer_product.get('product_id', '')}",
            retailer_id="instacart",
            retailer_sku=str(retailer_product.get("product_id", "")),
            upc=retailer_product.get("upc", ""),
            product_name=retailer_product.get("name", ""),
            brand=retailer_product.get("brand", ""),
            category=retailer_product.get("aisle", ""),
            subcategory=retailer_product.get("department", ""),
            price=retailer_product.get("price", 0.0),
            metadata={"instacart_id": retailer_product.get("product_id")}
        )
    
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        return {"7d": AttributionModel.LAST_CLICK}
    
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        return {
            "Produce": "CPG_FOOD",
            "Dairy": "CPG_FOOD",
            "Beverages": "CPG_BEVERAGES",
            "Household": "CPG_HOUSEHOLD",
            "Personal Care": "CPG_BEAUTY",
            "Baby": "CPG_BABY",
            "Pets": "CPG_PET",
        }
    
    def _parse_date(self, date_value: Any) -> datetime:
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            try:
                return datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                pass
        return datetime.now()
