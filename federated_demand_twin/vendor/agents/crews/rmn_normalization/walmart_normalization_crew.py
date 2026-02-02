"""
Walmart Connect Normalization Crew

Normalizes Walmart Connect (RMN) API data to canonical schema.
Based on Walmart Connect Sponsored Search API documentation.
"""

from typing import Dict, List, Any, Optional
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


class WalmartNormalizationCrew(BaseNormalizationCrew):
    """
    Walmart Connect Normalization Crew
    
    Handles normalization of Walmart Connect API data including:
    - Sponsored Products campaigns
    - Sponsored Brands campaigns
    - Sponsored Videos campaigns
    - Display Ads
    """
    
    # Walmart Connect API schema mappings
    WALMART_CAMPAIGN_TYPES = {
        "sponsoredProducts": AdFormat.SPONSORED_PRODUCT,
        "sponsoredBrands": AdFormat.SPONSORED_BRAND,
        "sponsoredVideos": AdFormat.SPONSORED_VIDEO,
        "display": AdFormat.DISPLAY,
    }
    
    WALMART_OBJECTIVES = {
        "SALES": CampaignObjective.CONVERSION,
        "AWARENESS": CampaignObjective.BRAND_AWARENESS,
        "CONSIDERATION": CampaignObjective.CONSIDERATION,
        "NTBR": CampaignObjective.CONVERSION,  # New-to-Brand Revenue
    }
    
    WALMART_STATUS_MAP = {
        "enabled": "active",
        "paused": "paused",
        "archived": "archived",
        "completed": "completed",
        "pending": "pending",
    }
    
    # Walmart attribution: 14-day click, 1-day view
    DEFAULT_ATTRIBUTION_WINDOW = 14
    
    def __init__(self, event_bus=None):
        super().__init__(
            retailer_id="walmart",
            retailer_name="Walmart",
            event_bus=event_bus
        )
    
    def get_retailer_schema(self) -> Dict[str, Any]:
        """Get Walmart Connect API schema definition"""
        return {
            "retailer": "walmart",
            "api_version": "v3",
            "endpoints": {
                "campaigns": "/api/v3/campaigns",
                "adGroups": "/api/v3/adGroups",
                "keywords": "/api/v3/keywords",
                "reports": "/api/v3/reports",
                "products": "/api/v3/items"
            },
            "campaign_schema": {
                "campaignId": {"type": "integer", "canonical": "campaign_id"},
                "name": {"type": "string", "canonical": "campaign_name"},
                "campaignType": {"type": "string", "canonical": "ad_format"},
                "targetingType": {"type": "string", "values": ["auto", "manual"]},
                "status": {"type": "string", "canonical": "status"},
                "budgetType": {"type": "string", "values": ["daily", "total"]},
                "dailyBudget": {"type": "float", "canonical": "daily_budget"},
                "totalBudget": {"type": "float", "canonical": "budget"},
                "startDate": {"type": "date", "canonical": "start_date"},
                "endDate": {"type": "date", "canonical": "end_date"},
                "advertiserId": {"type": "string", "canonical": "advertiser_id"},
                "biddingStrategy": {"type": "string", "values": ["fixed", "dynamic"]}
            },
            "performance_schema": {
                "date": {"type": "date", "canonical": "date"},
                "campaignId": {"type": "integer", "canonical": "campaign_id"},
                "impressions": {"type": "integer", "canonical": "impressions"},
                "clicks": {"type": "integer", "canonical": "clicks"},
                "spend": {"type": "float", "canonical": "spend"},
                "attributedSales14d": {"type": "float", "canonical": "revenue"},
                "attributedUnits14d": {"type": "integer", "canonical": "units_sold"},
                "attributedOrders14d": {"type": "integer", "canonical": "conversions"},
                "ntbRevenue14d": {"type": "float", "note": "New-to-Brand revenue"},
                "ntbUnits14d": {"type": "integer", "canonical": "new_to_brand"},
                "roas14d": {"type": "float", "canonical": "roas"}
            },
            "product_schema": {
                "itemId": {"type": "string", "canonical": "retailer_sku"},
                "upc": {"type": "string", "canonical": "upc"},
                "productName": {"type": "string", "canonical": "product_name"},
                "brand": {"type": "string", "canonical": "brand"},
                "primaryCategory": {"type": "string", "canonical": "category"},
                "secondaryCategory": {"type": "string", "canonical": "subcategory"},
                "price": {"type": "float", "canonical": "price"}
            }
        }
    
    def map_campaign(self, retailer_campaign: Dict[str, Any]) -> CanonicalCampaign:
        """Map Walmart Connect campaign to canonical format"""
        campaign_type = retailer_campaign.get("campaignType", "sponsoredProducts")
        ad_format = self.WALMART_CAMPAIGN_TYPES.get(campaign_type, AdFormat.SPONSORED_PRODUCT)
        
        objective_raw = retailer_campaign.get("objective", "SALES")
        objective = self.WALMART_OBJECTIVES.get(objective_raw, CampaignObjective.CONVERSION)
        
        status_raw = retailer_campaign.get("status", "enabled").lower()
        status = self.WALMART_STATUS_MAP.get(status_raw, "unknown")
        
        # Parse dates
        start_date = self._parse_date(retailer_campaign.get("startDate"))
        end_date = self._parse_date(retailer_campaign.get("endDate"))
        
        # Budget handling
        budget_type = retailer_campaign.get("budgetType", "daily")
        if budget_type == "daily":
            daily_budget = retailer_campaign.get("dailyBudget", 0)
            budget = retailer_campaign.get("totalBudget", daily_budget * 30)
        else:
            budget = retailer_campaign.get("totalBudget", 0)
            daily_budget = retailer_campaign.get("dailyBudget")
        
        return CanonicalCampaign(
            campaign_id=str(retailer_campaign.get("campaignId")),
            retailer_id="walmart",
            campaign_name=retailer_campaign.get("name", ""),
            advertiser_id=str(retailer_campaign.get("advertiserId", "")),
            objective=objective,
            budget=budget,
            daily_budget=daily_budget,
            start_date=start_date,
            end_date=end_date,
            status=status,
            ad_format=ad_format,
            targeting={
                "type": retailer_campaign.get("targetingType", "auto"),
                "bidding_strategy": retailer_campaign.get("biddingStrategy", "fixed")
            },
            metadata={
                "walmart_campaign_type": campaign_type,
                "budget_type": budget_type
            }
        )
    
    def map_performance(self, retailer_performance: Dict[str, Any]) -> CanonicalPerformance:
        """Map Walmart Connect performance metrics to canonical format"""
        date = self._parse_date(retailer_performance.get("date"))
        
        impressions = retailer_performance.get("impressions", 0)
        clicks = retailer_performance.get("clicks", 0)
        spend = retailer_performance.get("spend", 0.0)
        revenue = retailer_performance.get("attributedSales14d", 0.0)
        units_sold = retailer_performance.get("attributedUnits14d", 0)
        conversions = retailer_performance.get("attributedOrders14d", 0)
        new_to_brand = retailer_performance.get("ntbUnits14d", 0)
        
        # Calculate derived metrics
        roas = revenue / spend if spend > 0 else 0.0
        ctr = clicks / impressions if impressions > 0 else 0.0
        cpc = spend / clicks if clicks > 0 else 0.0
        cvr = conversions / clicks if clicks > 0 else 0.0
        
        return CanonicalPerformance(
            date=date,
            campaign_id=str(retailer_performance.get("campaignId")),
            retailer_id="walmart",
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            conversions=conversions,
            revenue=revenue,
            units_sold=units_sold,
            new_to_brand=new_to_brand,
            roas=roas,
            ctr=ctr,
            cpc=cpc,
            cvr=cvr,
            attribution_window=self.DEFAULT_ATTRIBUTION_WINDOW,
            attribution_model=AttributionModel.LAST_CLICK
        )
    
    def map_product(self, retailer_product: Dict[str, Any]) -> CanonicalProduct:
        """Map Walmart product to canonical format"""
        return CanonicalProduct(
            product_id=f"walmart_{retailer_product.get('itemId', '')}",
            retailer_id="walmart",
            retailer_sku=str(retailer_product.get("itemId", "")),
            upc=retailer_product.get("upc", ""),
            product_name=retailer_product.get("productName", ""),
            brand=retailer_product.get("brand", ""),
            category=retailer_product.get("primaryCategory", ""),
            subcategory=retailer_product.get("secondaryCategory", ""),
            price=retailer_product.get("price", 0.0),
            metadata={
                "walmart_item_id": retailer_product.get("itemId"),
                "shelf_category": retailer_product.get("shelfCategory")
            }
        )
    
    def get_attribution_mapping(self) -> Dict[str, AttributionModel]:
        """Get Walmart attribution type mappings"""
        return {
            "14d_click": AttributionModel.LAST_CLICK,
            "1d_view": AttributionModel.LAST_CLICK,
            "7d_click": AttributionModel.LAST_CLICK,
            "30d_click": AttributionModel.LAST_CLICK,
        }
    
    def get_taxonomy_mapping(self) -> Dict[str, str]:
        """Get Walmart category taxonomy mapping"""
        return {
            "Food": "CPG_FOOD",
            "Beverages": "CPG_BEVERAGES",
            "Household Essentials": "CPG_HOUSEHOLD",
            "Health": "CPG_HEALTH",
            "Beauty": "CPG_BEAUTY",
            "Baby": "CPG_BABY",
            "Pets": "CPG_PET",
            "Electronics": "CE_ELECTRONICS",
            "Home": "HOME_GOODS",
            "Clothing": "APPAREL",
            "Toys": "TOYS_GAMES",
            "Sports & Outdoors": "SPORTS_OUTDOOR",
            "Auto & Tires": "AUTO",
            "Pharmacy": "PHARMACY",
        }
    
    def _parse_date(self, date_value: Any) -> datetime:
        """Parse various date formats from Walmart API"""
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            # Try common formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
        return datetime.now()
