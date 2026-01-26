"""
Deterministic Synthetic Data Generator for RetailCo MVP

NFR-3.2: A deterministic synthetic dataset generator must exist so results can be reproduced.

Generates:
- sales_history: 2 years of weekly sales for 50 SKUs across 5 stores
- inventory_state: Current inventory positions
- supply_params: Supplier parameters (lead times, MOQ, case packs)
- hierarchy_map: SKU → subcategory → category → region mapping
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import hashlib
import json

# Add parent path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.schemas.data_contracts import (
    SalesHistory, InventoryState, SupplyParams, HierarchyMap
)


@dataclass
class GeneratorConfig:
    """Configuration for synthetic data generation"""
    # Seed for reproducibility
    seed: int = 42
    
    # Time range
    start_date: date = date(2022, 1, 3)  # First Monday of 2022
    end_date: date = date(2024, 1, 1)
    forecast_horizon_weeks: int = 13
    
    # Entity counts
    num_skus: int = 50
    num_stores: int = 5
    num_categories: int = 3
    num_subcategories: int = 10
    num_regions: int = 2
    num_suppliers: int = 8
    
    # Demand characteristics
    base_demand_range: Tuple[float, float] = (50.0, 500.0)
    trend_range: Tuple[float, float] = (-0.02, 0.05)  # Weekly trend
    seasonality_amplitude: float = 0.3
    noise_std: float = 0.15
    promo_lift: float = 0.4
    promo_probability: float = 0.15
    
    # Price characteristics
    base_price_range: Tuple[float, float] = (5.0, 100.0)
    price_elasticity: float = -1.5
    
    # Supply chain characteristics
    lead_time_range: Tuple[int, int] = (1, 6)
    moq_range: Tuple[int, int] = (12, 96)
    case_pack_options: List[int] = None
    
    # Inventory characteristics
    safety_stock_weeks: float = 2.0
    order_cycle_weeks: float = 4.0
    
    def __post_init__(self):
        if self.case_pack_options is None:
            self.case_pack_options = [6, 12, 24, 48]
    
    def config_hash(self) -> str:
        """Generate hash of configuration for reproducibility tracking"""
        config_dict = {
            'seed': self.seed,
            'start_date': str(self.start_date),
            'end_date': str(self.end_date),
            'num_skus': self.num_skus,
            'num_stores': self.num_stores,
        }
        return hashlib.md5(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()[:8]


class SyntheticRetailDataGenerator:
    """
    Deterministic generator for RetailCo synthetic data.
    
    Generates realistic retail demand patterns with:
    - Trend components (growth/decline)
    - Seasonal patterns (yearly cycle)
    - Promotional effects
    - Store-level variation
    - Price sensitivity
    """
    
    def __init__(self, config: Optional[GeneratorConfig] = None):
        self.config = config or GeneratorConfig()
        self.rng = np.random.default_rng(self.config.seed)
        
        # Pre-generate entity characteristics for consistency
        self._init_entity_characteristics()
    
    def _init_entity_characteristics(self):
        """Initialize stable characteristics for all entities"""
        cfg = self.config
        
        # SKU characteristics
        self.sku_ids = [f"SKU-{i:04d}" for i in range(cfg.num_skus)]
        self.sku_base_demand = self.rng.uniform(
            cfg.base_demand_range[0], cfg.base_demand_range[1], cfg.num_skus
        )
        self.sku_trend = self.rng.uniform(
            cfg.trend_range[0], cfg.trend_range[1], cfg.num_skus
        )
        self.sku_seasonality_phase = self.rng.uniform(0, 2 * np.pi, cfg.num_skus)
        self.sku_base_price = self.rng.uniform(
            cfg.base_price_range[0], cfg.base_price_range[1], cfg.num_skus
        )
        
        # Store characteristics
        self.store_ids = [f"STORE-{chr(65+i)}" for i in range(cfg.num_stores)]
        self.store_demand_multiplier = self.rng.uniform(0.7, 1.5, cfg.num_stores)
        
        # Hierarchy
        self.category_ids = [f"CAT-{i:02d}" for i in range(cfg.num_categories)]
        self.subcategory_ids = [f"SUBCAT-{i:02d}" for i in range(cfg.num_subcategories)]
        self.region_ids = [f"REGION-{i:02d}" for i in range(cfg.num_regions)]
        
        # Assign SKUs to hierarchy
        self.sku_to_subcategory = {
            sku: self.subcategory_ids[i % cfg.num_subcategories]
            for i, sku in enumerate(self.sku_ids)
        }
        self.subcategory_to_category = {
            subcat: self.category_ids[i % cfg.num_categories]
            for i, subcat in enumerate(self.subcategory_ids)
        }
        
        # Assign stores to regions
        self.store_to_region = {
            store: self.region_ids[i % cfg.num_regions]
            for i, store in enumerate(self.store_ids)
        }
        
        # Supplier assignments
        self.supplier_ids = [f"SUPPLIER-{i:02d}" for i in range(cfg.num_suppliers)]
        self.sku_to_supplier = {
            sku: self.supplier_ids[i % cfg.num_suppliers]
            for i, sku in enumerate(self.sku_ids)
        }
    
    def _get_weeks(self) -> List[date]:
        """Generate list of week start dates"""
        weeks = []
        current = self.config.start_date
        while current < self.config.end_date:
            weeks.append(current)
            current += timedelta(days=7)
        return weeks
    
    def _compute_demand(
        self, 
        sku_idx: int, 
        store_idx: int, 
        week_idx: int,
        price_ratio: float = 1.0,
        promo: bool = False
    ) -> float:
        """
        Compute demand for a SKU-store-week combination.
        
        Demand = base × trend × seasonality × store_effect × price_effect × promo_effect × noise
        """
        cfg = self.config
        
        # Base demand
        base = self.sku_base_demand[sku_idx]
        
        # Trend effect (compound weekly growth)
        trend = (1 + self.sku_trend[sku_idx]) ** week_idx
        
        # Seasonality (yearly cycle with SKU-specific phase)
        season_period = 52  # weeks
        phase = self.sku_seasonality_phase[sku_idx]
        seasonality = 1 + cfg.seasonality_amplitude * np.sin(
            2 * np.pi * week_idx / season_period + phase
        )
        
        # Store effect
        store_effect = self.store_demand_multiplier[store_idx]
        
        # Price effect (log-linear elasticity)
        price_effect = price_ratio ** cfg.price_elasticity
        
        # Promo effect
        promo_effect = 1 + cfg.promo_lift if promo else 1.0
        
        # Noise (multiplicative)
        noise = 1 + self.rng.normal(0, cfg.noise_std)
        
        # Combine effects
        demand = base * trend * seasonality * store_effect * price_effect * promo_effect * noise
        
        return max(0, demand)  # Ensure non-negative
    
    def generate_sales_history(self) -> pd.DataFrame:
        """
        Generate sales_history table.
        
        FR-1.1: Raw sales data (private, never exported)
        """
        cfg = self.config
        weeks = self._get_weeks()
        
        records = []
        for week_idx, week_start in enumerate(weeks):
            for sku_idx, sku_id in enumerate(self.sku_ids):
                for store_idx, store_id in enumerate(self.store_ids):
                    # Determine if promo
                    # Use deterministic seed based on week/sku/store
                    promo_seed = hash((week_start.isoformat(), sku_id, store_id)) % 1000
                    promo = promo_seed < (cfg.promo_probability * 1000)
                    
                    # Price (with promo discount)
                    base_price = self.sku_base_price[sku_idx]
                    price = base_price * (0.8 if promo else 1.0)  # 20% discount on promo
                    price_ratio = price / base_price
                    
                    # Compute demand
                    units = self._compute_demand(
                        sku_idx, store_idx, week_idx, price_ratio, promo
                    )
                    units = round(units)  # Integer units
                    
                    revenue = units * price
                    
                    records.append({
                        'sku_id': sku_id,
                        'store_id': store_id,
                        'week_start': week_start,
                        'units': float(units),
                        'revenue': round(revenue, 2),
                        'price': round(price, 2),
                        'promo_flag': promo
                    })
        
        df = pd.DataFrame(records)
        return df
    
    def generate_inventory_state(self, sales_df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate inventory_state table based on sales history.
        
        Simulates inventory positions as of the most recent week.
        """
        cfg = self.config
        
        # Get latest week
        latest_week = sales_df['week_start'].max()
        
        records = []
        for sku_id in self.sku_ids:
            for store_id in self.store_ids:
                # Get recent sales for this SKU-store
                mask = (
                    (sales_df['sku_id'] == sku_id) & 
                    (sales_df['store_id'] == store_id)
                )
                recent_sales = sales_df[mask].tail(cfg.forecast_horizon_weeks)
                
                if len(recent_sales) == 0:
                    continue
                
                # Average weekly demand
                avg_demand = recent_sales['units'].mean()
                
                # Safety stock + cycle stock
                safety_stock = avg_demand * cfg.safety_stock_weeks
                cycle_stock = avg_demand * cfg.order_cycle_weeks / 2
                
                # Add some randomness
                on_hand = max(0, round(
                    (safety_stock + cycle_stock) * self.rng.uniform(0.5, 1.5)
                ))
                
                # On order (probability-based)
                on_order = round(
                    avg_demand * cfg.order_cycle_weeks * self.rng.choice([0, 0.5, 1.0])
                )
                
                # Backorders (rare)
                backorders = round(
                    avg_demand * 0.1 if self.rng.random() < 0.1 else 0
                )
                
                records.append({
                    'sku_id': sku_id,
                    'store_id': store_id,
                    'week_start': latest_week,
                    'on_hand': float(on_hand),
                    'on_order': float(on_order),
                    'backorders': float(backorders)
                })
        
        return pd.DataFrame(records)
    
    def generate_supply_params(self) -> pd.DataFrame:
        """
        Generate supply_params table.
        """
        cfg = self.config
        
        records = []
        for sku_idx, sku_id in enumerate(self.sku_ids):
            supplier_id = self.sku_to_supplier[sku_id]
            
            # Lead time (varies by supplier with some SKU variation)
            supplier_idx = int(supplier_id.split('-')[1])
            base_lead_time = cfg.lead_time_range[0] + (
                supplier_idx % (cfg.lead_time_range[1] - cfg.lead_time_range[0])
            )
            lead_time = base_lead_time + self.rng.integers(-1, 2)
            lead_time = max(cfg.lead_time_range[0], min(cfg.lead_time_range[1], lead_time))
            
            # MOQ
            moq = int(self.rng.choice(range(cfg.moq_range[0], cfg.moq_range[1], 12)))
            
            # Case pack
            case_pack = int(self.rng.choice(cfg.case_pack_options))
            
            # Capacity flags
            capacity_flags = {
                'seasonal_limit': bool(self.rng.random() < 0.1),
                'warehouse_constrained': bool(self.rng.random() < 0.05),
            }
            
            records.append({
                'sku_id': sku_id,
                'supplier_id': supplier_id,
                'lead_time_weeks': int(lead_time),
                'moq': moq,
                'case_pack': case_pack,
                'capacity_flags': capacity_flags
            })
        
        return pd.DataFrame(records)
    
    def generate_hierarchy_map(self) -> pd.DataFrame:
        """
        Generate hierarchy_map table.
        """
        records = []
        for sku_id in self.sku_ids:
            subcategory_id = self.sku_to_subcategory[sku_id]
            category_id = self.subcategory_to_category[subcategory_id]
            
            # For simplicity, assign region based on first character of SKU
            region_idx = hash(sku_id) % len(self.region_ids)
            region_id = self.region_ids[region_idx]
            
            records.append({
                'sku_id': sku_id,
                'subcategory_id': subcategory_id,
                'category_id': category_id,
                'region_id': region_id
            })
        
        return pd.DataFrame(records)
    
    def generate_all(self) -> Dict[str, pd.DataFrame]:
        """
        Generate all tables.
        
        Returns dict with keys:
        - sales_history
        - inventory_state
        - supply_params
        - hierarchy_map
        """
        print(f"Generating synthetic data with config hash: {self.config.config_hash()}")
        print(f"  SKUs: {self.config.num_skus}")
        print(f"  Stores: {self.config.num_stores}")
        print(f"  Date range: {self.config.start_date} to {self.config.end_date}")
        
        sales = self.generate_sales_history()
        print(f"  Generated {len(sales):,} sales records")
        
        inventory = self.generate_inventory_state(sales)
        print(f"  Generated {len(inventory):,} inventory records")
        
        supply = self.generate_supply_params()
        print(f"  Generated {len(supply):,} supply param records")
        
        hierarchy = self.generate_hierarchy_map()
        print(f"  Generated {len(hierarchy):,} hierarchy records")
        
        return {
            'sales_history': sales,
            'inventory_state': inventory,
            'supply_params': supply,
            'hierarchy_map': hierarchy
        }
    
    def save_to_parquet(self, output_dir: Path) -> Dict[str, Path]:
        """Save all tables to parquet files"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = self.generate_all()
        paths = {}
        
        for name, df in data.items():
            path = output_dir / f"{name}.parquet"
            df.to_parquet(path, index=False)
            paths[name] = path
            print(f"  Saved {name} to {path}")
        
        # Save config
        config_path = output_dir / "generator_config.json"
        with open(config_path, 'w') as f:
            json.dump({
                'config_hash': self.config.config_hash(),
                'seed': self.config.seed,
                'start_date': str(self.config.start_date),
                'end_date': str(self.config.end_date),
                'num_skus': self.config.num_skus,
                'num_stores': self.config.num_stores,
            }, f, indent=2)
        
        return paths


def generate_training_data(
    output_dir: str = "./data/customer",
    seed: int = 42
) -> Dict[str, pd.DataFrame]:
    """
    Convenience function to generate training data.
    """
    config = GeneratorConfig(seed=seed)
    generator = SyntheticRetailDataGenerator(config)
    
    output_path = Path(output_dir)
    generator.save_to_parquet(output_path)
    
    return generator.generate_all()


if __name__ == "__main__":
    # Generate sample data
    data = generate_training_data("./data/customer")
    
    print("\n=== Sample Data ===")
    for name, df in data.items():
        print(f"\n{name}:")
        print(df.head())
        print(f"Shape: {df.shape}")
