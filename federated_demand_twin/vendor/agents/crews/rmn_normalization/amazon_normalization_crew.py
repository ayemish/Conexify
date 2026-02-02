"""
Amazon Ads Normalization Crew

Normalizes Amazon Advertising API data to canonical schema.
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


class AmazonNormalizationCrew(BaseNormalizationCrew):
    """Amazon Advertising Normalization Crew"""
    
    AMAZON_AD_FORMATS = {
        "sponsoredProducts": AdFormat.SPONSORED_PRODUCT,
        "sponsoredBrands": AdFormat.SPONSORED_BRAND,
        "sponsoredDisplay": AdFormat.DISPLAY,
        "dsp": AdFormat.DISPLAY,
    }
    
    AMAZON_OBJECTIVES = {
        "reach": CampaignObjective.BRAND_AWARENESS,
        "pageVisits": CampaignObjective.CONSIDERATION,
        "conversions": CampaignObjective.CONVERSION,
    }
    
    DEFAULT_ATTRIBUTION_WINDOW = 14
    
    def __init__(self, event_bus=None):
        super().__init__(
            retailer_id="amazon",
            retailer_name="Amazon",
            event_bus=event_bus
        )
    
    def get_retailer_schema(self) -> Dict[str, Any]:
        return {
            "retailer": "amazon",
            "api_version": "v3",
            "campaign_schema": {
                "campaignId": {"type": "integer", "canonical": "campaign_id"},
                "name": {"type": "string", "canonical": "campaign_name"},
                "campaignType": {"type": "string", "canonical": "ad_format"},
                "state": {"type": "string", "canonical": "status"},
                "budget": {"type": "float", "canonical": "budget"},
                "startDate": {"type": "string", "canonical": "start_date"},
                "endDate": {"type": "string", "canonical": "end_date"},
            }
        }
    
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        ad_format = self.AMAZON_AD_FORMATS.get(
            retailer_campaign.get("campaignType", "sponsoredProducts"), AdFormat.SPONSORED_PRODUCT
        )
        
        return CanonicalCampaign(
            campaign_id=str(retailer_campaign.get("campaignId")),
            retailer_id="amazon",
            campaign_name=retailer_campaign.get("name", ""),
            advertiser_id=str(retailer_campaign.get("advertiserId", "")),
            objective=CampaignObjective.CONVERSION,
            budget=retailer_campaign.get("budget", 0),
            daily_budget=retailer_campaign.get("dailyBudget"),
            start_date=self._parse_date(retailer_campaign.get("startDate")),
            end_date=self._parse_date(retailer_campaign.get("endDate")),
            status=retailer_campaign.get("state", "enabled"),
            ad_format=ad_format,
            targeting=retailer_campaign.get("targeting", {}),
            metadata={"source": "amazon_ads"}
        )
    
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        impressions = retailer_performance.get("impressions", 0)
        clicks = retailer_performance.get("clicks", 0)
        spend = retailer_performance.get("cost", 0.0)
        revenue = retailer_performance.get("attributedSales14d", 0.0)
        conversions = retailer_performance.get("attributedConversions14d", 0)
        
        return CanonicalPerformance(
            date=self._parse_date(retailer_performance.get("date")),
            campaign_id=str(retailer_performance.get("campaignId")),
            retailer_id="amazon",
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=conversions,
            revenue=revenue,
            units_sold=retailer_performance.get("attributedUnitsOrdered14d", 0),
            new_to_brand=retailer_performance.get("newToBrandPurchases14d", 0),
            roas=revenue / spend if spend > 0 else 0,
            ctr=clicks / impressions if impressions > 0 else 0,
            cpc=spend / clicks if clicks > 0 else 0,
            cvr=conversions / clicks if clicks > 0 else 0,
            attribution_window=self.DEFAULT_ATTRIBUTION_WINDOW,
            attribution_model=AttributionModel.LAST_CLICK
        )
    
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        return CanonicalProduct(
            product_id=f"amazon_{retailer_product.get('asin', '')}",
            retailer_id="amazon",
            retailer_sku=str(retailer_product.get("asin", "")),
            upc=retailer_product.get("upc", ""),
            product_name=retailer_product.get("title", ""),
            brand=retailer_product.get("brand", ""),
            category=retailer_product.get("browseNode", ""),
            subcategory=retailer_product.get("subBrowseNode", ""),
            price=retailer_product.get("price", 0.0),
            metadata={"asin": retailer_product.get("asin")}
        )
    
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        return {
            "14d": AttributionModel.LAST_CLICK,
            "7d": AttributionModel.LAST_CLICK,
            "1d": AttributionModel.LAST_CLICK,
        }
    
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        return {
            "Grocery & Gourmet Food": "CPG_FOOD",
            "Health & Household": "CPG_HOUSEHOLD",
            "Beauty & Personal Care": "CPG_BEAUTY",
            "Baby": "CPG_BABY",
            "Pet Supplies": "CPG_PET",
        }
    
    def _parse_date(self, date_value: Any) -> datetime:
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            for fmt in ["%Y-%m-%d", "%Y%m%d"]:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
        return datetime.now()
