"""
Target Roundel Normalization Crew

Normalizes Target Roundel (RMN) data to canonical schema.
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


class TargetNormalizationCrew(BaseNormalizationCrew):
    """Target Roundel Normalization Crew"""
    
    TARGET_AD_FORMATS = {
        "search": AdFormat.SEARCH,
        "display": AdFormat.DISPLAY,
        "video": AdFormat.SPONSORED_VIDEO,
        "native": AdFormat.NATIVE,
    }
    
    TARGET_OBJECTIVES = {
        "awareness": CampaignObjective.BRAND_AWARENESS,
        "consideration": CampaignObjective.CONSIDERATION,
        "conversion": CampaignObjective.CONVERSION,
    }
    
    DEFAULT_ATTRIBUTION_WINDOW = 14
    
    def __init__(self, event_bus=None):
        super().__init__(
            retailer_id="target",
            retailer_name="Target",
            event_bus=event_bus
        )
    
    def get_retailer_schema(self) -> Dict[str, Any]:
        return {
            "retailer": "target",
            "api_version": "v2",
            "campaign_schema": {
                "id": {"type": "string", "canonical": "campaign_id"},
                "name": {"type": "string", "canonical": "campaign_name"},
                "adType": {"type": "string", "canonical": "ad_format"},
                "objective": {"type": "string", "canonical": "objective"},
                "budget": {"type": "float", "canonical": "budget"},
                "startDate": {"type": "date", "canonical": "start_date"},
                "endDate": {"type": "date", "canonical": "end_date"},
                "status": {"type": "string", "canonical": "status"},
            }
        }
    
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        ad_format = self.TARGET_AD_FORMATS.get(
            retailer_campaign.get("adType", "search"), AdFormat.SEARCH
        )
        objective = self.TARGET_OBJECTIVES.get(
            retailer_campaign.get("objective", "conversion"), CampaignObjective.CONVERSION
        )
        
        return CanonicalCampaign(
            campaign_id=str(retailer_campaign.get("id")),
            retailer_id="target",
            campaign_name=retailer_campaign.get("name", ""),
            advertiser_id=str(retailer_campaign.get("advertiserId", "")),
            objective=objective,
            budget=retailer_campaign.get("budget", 0),
            daily_budget=retailer_campaign.get("dailyBudget"),
            start_date=self._parse_date(retailer_campaign.get("startDate")),
            end_date=self._parse_date(retailer_campaign.get("endDate")),
            status=retailer_campaign.get("status", "active"),
            ad_format=ad_format,
            targeting=retailer_campaign.get("targeting", {}),
            metadata={"source": "target_roundel"}
        )
    
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        impressions = retailer_performance.get("impressions", 0)
        clicks = retailer_performance.get("clicks", 0)
        spend = retailer_performance.get("spend", 0.0)
        revenue = retailer_performance.get("sales", 0.0)
        conversions = retailer_performance.get("orders", 0)
        
        return CanonicalPerformance(
            date=self._parse_date(retailer_performance.get("date")),
            campaign_id=str(retailer_performance.get("campaignId")),
            retailer_id="target",
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=conversions,
            revenue=revenue,
            units_sold=retailer_performance.get("units", 0),
            new_to_brand=retailer_performance.get("newGuests", 0),
            roas=revenue / spend if spend > 0 else 0,
            ctr=clicks / impressions if impressions > 0 else 0,
            cpc=spend / clicks if clicks > 0 else 0,
            cvr=conversions / clicks if clicks > 0 else 0,
            attribution_window=self.DEFAULT_ATTRIBUTION_WINDOW,
            attribution_model=AttributionModel.LAST_CLICK
        )
    
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        return CanonicalProduct(
            product_id=f"target_{retailer_product.get('tcin', '')}",
            retailer_id="target",
            retailer_sku=str(retailer_product.get("tcin", "")),
            upc=retailer_product.get("upc", ""),
            product_name=retailer_product.get("title", ""),
            brand=retailer_product.get("brand", ""),
            category=retailer_product.get("category", ""),
            subcategory=retailer_product.get("subcategory", ""),
            price=retailer_product.get("price", 0.0),
            metadata={"tcin": retailer_product.get("tcin")}
        )
    
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        return {"14d_click": AttributionModel.LAST_CLICK}
    
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        return {
            "Grocery": "CPG_FOOD",
            "Household Essentials": "CPG_HOUSEHOLD",
            "Beauty": "CPG_BEAUTY",
            "Health": "CPG_HEALTH",
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
