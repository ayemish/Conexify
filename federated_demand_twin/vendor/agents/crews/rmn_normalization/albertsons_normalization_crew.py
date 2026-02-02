"""
Albertsons Media Collective Normalization Crew

Normalizes Albertsons Media Collective data to canonical schema.
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


class AlbertsonsNormalizationCrew(BaseNormalizationCrew):
    """Albertsons Media Collective Normalization Crew"""
    
    ALBERTSONS_AD_FORMATS = {
        "sponsored_search": AdFormat.SEARCH,
        "display": AdFormat.DISPLAY,
        "in_store": AdFormat.IN_STORE,
        "offsite": AdFormat.DISPLAY,
    }
    
    DEFAULT_ATTRIBUTION_WINDOW = 14
    
    def __init__(self, event_bus=None):
        super().__init__(
            retailer_id="albertsons",
            retailer_name="Albertsons",
            event_bus=event_bus
        )
    
    def get_retailer_schema(self) -> Dict[str, Any]:
        return {
            "retailer": "albertsons",
            "api_version": "v1",
            "banners": ["Albertsons", "Safeway", "Vons", "Jewel-Osco", "Acme", "Shaw's"],
            "campaign_schema": {
                "campaign_id": {"type": "string", "canonical": "campaign_id"},
                "campaign_name": {"type": "string", "canonical": "campaign_name"},
                "placement_type": {"type": "string", "canonical": "ad_format"},
                "status": {"type": "string", "canonical": "status"},
                "budget": {"type": "float", "canonical": "budget"},
                "flight_start": {"type": "date", "canonical": "start_date"},
                "flight_end": {"type": "date", "canonical": "end_date"},
            }
        }
    
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        ad_format = self.ALBERTSONS_AD_FORMATS.get(
            retailer_campaign.get("placement_type", "sponsored_search"), AdFormat.SEARCH
        )
        
        return CanonicalCampaign(
            campaign_id=str(retailer_campaign.get("campaign_id")),
            retailer_id="albertsons",
            campaign_name=retailer_campaign.get("campaign_name", ""),
            advertiser_id=str(retailer_campaign.get("advertiser_id", "")),
            objective=CampaignObjective.CONVERSION,
            budget=retailer_campaign.get("budget", 0),
            daily_budget=retailer_campaign.get("daily_budget"),
            start_date=self._parse_date(retailer_campaign.get("flight_start")),
            end_date=self._parse_date(retailer_campaign.get("flight_end")),
            status=retailer_campaign.get("status", "active"),
            ad_format=ad_format,
            targeting=retailer_campaign.get("targeting", {}),
            metadata={
                "source": "albertsons_media_collective",
                "banners": retailer_campaign.get("banners", [])
            }
        )
    
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        impressions = retailer_performance.get("impressions", 0)
        clicks = retailer_performance.get("clicks", 0)
        spend = retailer_performance.get("media_cost", 0.0)
        revenue = retailer_performance.get("attributed_sales", 0.0)
        conversions = retailer_performance.get("transactions", 0)
        
        return CanonicalPerformance(
            date=self._parse_date(retailer_performance.get("date")),
            campaign_id=str(retailer_performance.get("campaign_id")),
            retailer_id="albertsons",
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=conversions,
            revenue=revenue,
            units_sold=retailer_performance.get("units_sold", 0),
            new_to_brand=retailer_performance.get("new_buyers", 0),
            roas=revenue / spend if spend > 0 else 0,
            ctr=clicks / impressions if impressions > 0 else 0,
            cpc=spend / clicks if clicks > 0 else 0,
            cvr=conversions / clicks if clicks > 0 else 0,
            attribution_window=self.DEFAULT_ATTRIBUTION_WINDOW,
            attribution_model=AttributionModel.LAST_CLICK
        )
    
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        return CanonicalProduct(
            product_id=f"albertsons_{retailer_product.get('sku', '')}",
            retailer_id="albertsons",
            retailer_sku=str(retailer_product.get("sku", "")),
            upc=retailer_product.get("upc", ""),
            product_name=retailer_product.get("product_name", ""),
            brand=retailer_product.get("brand", ""),
            category=retailer_product.get("department", ""),
            subcategory=retailer_product.get("category", ""),
            price=retailer_product.get("price", 0.0),
            metadata={
                "albertsons_sku": retailer_product.get("sku"),
                "banner": retailer_product.get("banner")
            }
        )
    
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        return {"14d": AttributionModel.LAST_CLICK}
    
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        return {
            "Grocery": "CPG_FOOD",
            "Dairy": "CPG_FOOD",
            "Beverages": "CPG_BEVERAGES",
            "Household": "CPG_HOUSEHOLD",
            "Health & Beauty": "CPG_BEAUTY",
            "Baby": "CPG_BABY",
            "Pet": "CPG_PET",
            "Pharmacy": "PHARMACY",
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
