"""
Federated Learning Client for RetailCo

FR-2.2: Federated client performs local training on private data and 
transmits model updates (not raw sales).

FR-2.4: Support configuration toggles for secure aggregation and 
differential privacy.

Implements Flower client interface for federated demand forecasting.
"""

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path

# Flower imports (will be installed via requirements)
try:
    import flwr as fl
    from flwr.common import (
        Code, EvaluateIns, EvaluateRes, FitIns, FitRes,
        GetParametersIns, GetParametersRes, Status,
        ndarrays_to_parameters, parameters_to_ndarrays
    )
    FLOWER_AVAILABLE = True
except ImportError:
    FLOWER_AVAILABLE = False
    logging.warning("Flower not installed. Using mock client.")

from .demand_model import FederatedDemandModel, ModelConfig, create_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """Configuration for federated learning client"""
    client_id: str = "retailco-client-1"
    data_path: str = "./data/customer"
    
    # Privacy settings (FR-2.4)
    enable_secure_aggregation: bool = False
    enable_differential_privacy: bool = False
    dp_epsilon: float = 1.0
    dp_delta: float = 1e-5
    dp_max_grad_norm: float = 1.0
    
    # Training settings
    local_epochs: int = 3
    batch_size: int = 32
    validation_split: float = 0.2
    
    # Logging
    log_metrics: bool = True
    metrics_path: str = "./logs/client_metrics.json"


class DemandForecastDataset(Dataset):
    """
    PyTorch dataset for demand forecasting.
    
    Creates sliding windows of historical demand for training.
    """
    
    def __init__(
        self,
        sales_df: pd.DataFrame,
        lookback: int = 26,
        horizon: int = 13,
        entity_col: str = 'sku_id'
    ):
        self.lookback = lookback
        self.horizon = horizon
        self.samples = []
        
        # Create samples for each entity
        for entity_id in sales_df[entity_col].unique():
            entity_data = sales_df[sales_df[entity_col] == entity_id].sort_values('week_start')
            
            demand = entity_data['units'].values
            prices = entity_data['price'].values
            promos = entity_data['promo_flag'].astype(float).values
            
            # Create sliding windows
            for i in range(len(demand) - lookback - horizon + 1):
                history = demand[i:i + lookback]
                target = demand[i + lookback:i + lookback + horizon]
                
                # Covariates: price ratio, promo, week-of-year sin/cos
                price_history = prices[i:i + lookback]
                promo_history = promos[i:i + lookback]
                
                # Week of year encoding (seasonal)
                week_idx = np.arange(i, i + lookback)
                week_sin = np.sin(2 * np.pi * week_idx / 52)
                week_cos = np.cos(2 * np.pi * week_idx / 52)
                
                # Normalize price to ratio
                price_ratio = price_history / (price_history.mean() + 1e-8)
                
                covariates = np.stack([
                    price_ratio,
                    promo_history,
                    week_sin,
                    week_cos,
                    np.ones(lookback) * (i / len(demand))  # Trend position
                ], axis=-1)
                
                self.samples.append({
                    'demand_history': history.astype(np.float32),
                    'covariates': covariates.astype(np.float32),
                    'targets': target.astype(np.float32),
                    'entity_id': entity_id
                })
    
    def __len__(self) -> int:
        return len(self.samples)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]
        return {
            'demand_history': torch.from_numpy(sample['demand_history']),
            'covariates': torch.from_numpy(sample['covariates']),
            'targets': torch.from_numpy(sample['targets']),
        }


class DifferentialPrivacyHandler:
    """
    Differential privacy utilities for gradient clipping and noise addition.
    
    FR-2.4: Support differential privacy toggle
    """
    
    def __init__(self, epsilon: float, delta: float, max_grad_norm: float):
        self.epsilon = epsilon
        self.delta = delta
        self.max_grad_norm = max_grad_norm
    
    def clip_gradients(self, model: torch.nn.Module) -> float:
        """Clip gradients to max norm"""
        total_norm = torch.nn.utils.clip_grad_norm_(
            model.parameters(), 
            self.max_grad_norm
        )
        return total_norm.item()
    
    def add_noise_to_parameters(
        self, 
        parameters: List[np.ndarray],
        num_samples: int
    ) -> List[np.ndarray]:
        """Add calibrated Gaussian noise for DP"""
        # Simplified noise calibration
        sigma = self.max_grad_norm * np.sqrt(2 * np.log(1.25 / self.delta)) / self.epsilon
        noise_scale = sigma / num_samples
        
        noisy_params = []
        for param in parameters:
            noise = np.random.normal(0, noise_scale, param.shape)
            noisy_params.append(param + noise.astype(param.dtype))
        
        return noisy_params


class RetailCoFlowerClient:
    """
    Flower client implementation for RetailCo federated learning.
    
    Handles:
    - Local model training on private sales data
    - Parameter extraction and transmission
    - Privacy controls (DP, secure aggregation flags)
    - Metrics logging
    """
    
    def __init__(
        self,
        config: ClientConfig,
        model_config: Optional[ModelConfig] = None
    ):
        self.config = config
        self.model_config = model_config or ModelConfig()
        
        # Initialize model
        self.federated_model = create_model(self.model_config)
        
        # Privacy handler
        if config.enable_differential_privacy:
            self.dp_handler = DifferentialPrivacyHandler(
                config.dp_epsilon,
                config.dp_delta,
                config.dp_max_grad_norm
            )
        else:
            self.dp_handler = None
        
        # Data loaders (lazy initialization)
        self._train_loader = None
        self._val_loader = None
        
        # Metrics tracking
        self.round_metrics = []
    
    def load_data(self, sales_df: Optional[pd.DataFrame] = None):
        """Load and prepare training data"""
        if sales_df is None:
            # Load from parquet
            data_path = Path(self.config.data_path)
            sales_path = data_path / "sales_history.parquet"
            
            if not sales_path.exists():
                raise FileNotFoundError(f"Sales data not found at {sales_path}")
            
            sales_df = pd.read_parquet(sales_path)
        
        logger.info(f"Loaded {len(sales_df):,} sales records")
        
        # Create dataset
        dataset = DemandForecastDataset(
            sales_df,
            lookback=self.model_config.lookback_weeks,
            horizon=self.model_config.forecast_horizon
        )
        
        logger.info(f"Created {len(dataset):,} training samples")
        
        # Split into train/val
        val_size = int(len(dataset) * self.config.validation_split)
        train_size = len(dataset) - val_size
        
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset, [train_size, val_size]
        )
        
        self._train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True
        )
        
        self._val_loader = DataLoader(
            val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False
        )
        
        logger.info(f"Train samples: {train_size}, Val samples: {val_size}")
    
    def get_parameters(self) -> List[np.ndarray]:
        """Get current model parameters"""
        return self.federated_model.get_parameters()
    
    def set_parameters(self, parameters: List[np.ndarray]):
        """Set model parameters from server"""
        self.federated_model.set_parameters(parameters)
    
    def fit(
        self, 
        parameters: List[np.ndarray],
        config: Dict[str, Any]
    ) -> Tuple[List[np.ndarray], int, Dict[str, float]]:
        """
        Train model on local data.
        
        FR-2.2: Local training on private data
        
        Returns:
            Updated parameters, number of samples, metrics dict
        """
        # Set global model parameters
        self.set_parameters(parameters)
        
        # Ensure data is loaded
        if self._train_loader is None:
            self.load_data()
        
        # Get round info from config
        round_num = config.get('round', 0)
        local_epochs = config.get('local_epochs', self.config.local_epochs)
        
        logger.info(f"Starting local training for round {round_num}")
        
        # Train for local epochs
        total_loss = 0.0
        num_batches = 0
        
        for epoch in range(local_epochs):
            epoch_metrics = self.federated_model.train_epoch(self._train_loader)
            total_loss += epoch_metrics['loss']
            num_batches += epoch_metrics['num_batches']
            
            # Apply DP gradient clipping if enabled
            if self.dp_handler is not None:
                # Note: In production, clipping would be per-sample
                pass
        
        avg_loss = total_loss / local_epochs
        
        # Get updated parameters
        updated_params = self.get_parameters()
        
        # Apply DP noise if enabled
        if self.dp_handler is not None and self.config.enable_differential_privacy:
            num_samples = len(self._train_loader.dataset)
            updated_params = self.dp_handler.add_noise_to_parameters(
                updated_params, num_samples
            )
            logger.info(f"Applied DP noise with ε={self.config.dp_epsilon}")
        
        # Collect metrics
        num_samples = len(self._train_loader.dataset)
        metrics = {
            'loss': avg_loss,
            'num_samples': num_samples,
            'local_epochs': local_epochs,
            'dp_enabled': self.config.enable_differential_privacy,
            'dp_epsilon': self.config.dp_epsilon if self.config.enable_differential_privacy else 0.0,
        }
        
        # Log metrics
        self._log_round_metrics(round_num, metrics)
        
        logger.info(f"Round {round_num} complete. Loss: {avg_loss:.4f}")
        
        return updated_params, num_samples, metrics
    
    def evaluate(
        self,
        parameters: List[np.ndarray],
        config: Dict[str, Any]
    ) -> Tuple[float, int, Dict[str, float]]:
        """
        Evaluate model on local validation data.
        
        Returns:
            Loss, number of samples, metrics dict
        """
        self.set_parameters(parameters)
        
        if self._val_loader is None:
            self.load_data()
        
        eval_metrics = self.federated_model.evaluate(self._val_loader)
        
        loss = eval_metrics['val_loss']
        num_samples = eval_metrics['num_samples']
        
        return loss, num_samples, {'val_loss': loss}
    
    def _log_round_metrics(self, round_num: int, metrics: Dict[str, Any]):
        """Log metrics for audit trail"""
        if not self.config.log_metrics:
            return
        
        log_entry = {
            'round': round_num,
            'client_id': self.config.client_id,
            'timestamp': datetime.utcnow().isoformat(),
            'privacy_mode': {
                'secure_aggregation': self.config.enable_secure_aggregation,
                'differential_privacy': self.config.enable_differential_privacy,
            },
            'metrics': metrics
        }
        
        self.round_metrics.append(log_entry)
        
        # Write to file
        metrics_path = Path(self.config.metrics_path)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(metrics_path, 'w') as f:
            json.dump(self.round_metrics, f, indent=2)


if FLOWER_AVAILABLE:
    class FlowerDemandClient(fl.client.NumPyClient):
        """
        Flower NumPyClient wrapper for RetailCo client.
        
        This is the actual Flower client interface that gets registered
        with the Flower server.
        """
        
        def __init__(self, retailco_client: RetailCoFlowerClient):
            self.client = retailco_client
        
        def get_parameters(self, config: Dict[str, Any]) -> List[np.ndarray]:
            return self.client.get_parameters()
        
        def fit(
            self,
            parameters: List[np.ndarray],
            config: Dict[str, Any]
        ) -> Tuple[List[np.ndarray], int, Dict[str, float]]:
            return self.client.fit(parameters, config)
        
        def evaluate(
            self,
            parameters: List[np.ndarray],
            config: Dict[str, Any]
        ) -> Tuple[float, int, Dict[str, float]]:
            return self.client.evaluate(parameters, config)


def create_flower_client(
    client_config: Optional[ClientConfig] = None,
    model_config: Optional[ModelConfig] = None,
    sales_df: Optional[pd.DataFrame] = None
):
    """
    Factory function to create a Flower client.
    
    Args:
        client_config: Client configuration
        model_config: Model architecture configuration
        sales_df: Optional pre-loaded sales data
    
    Returns:
        Flower client instance
    """
    client_config = client_config or ClientConfig()
    model_config = model_config or ModelConfig()
    
    retailco_client = RetailCoFlowerClient(client_config, model_config)
    
    if sales_df is not None:
        retailco_client.load_data(sales_df)
    
    if FLOWER_AVAILABLE:
        return FlowerDemandClient(retailco_client)
    else:
        logger.warning("Flower not available, returning base client")
        return retailco_client


def start_client(
    server_address: str = "localhost:8080",
    client_config: Optional[ClientConfig] = None,
    model_config: Optional[ModelConfig] = None
):
    """
    Start the Flower client and connect to server.
    
    FR-2.2: Run federated client that performs local training
    """
    if not FLOWER_AVAILABLE:
        raise ImportError("Flower is required to start client. Install with: pip install flwr")
    
    client = create_flower_client(client_config, model_config)
    
    logger.info(f"Starting Flower client, connecting to {server_address}")
    
    fl.client.start_numpy_client(
        server_address=server_address,
        client=client
    )


if __name__ == "__main__":
    # Test client creation
    config = ClientConfig(
        client_id="test-client",
        enable_differential_privacy=True,
        dp_epsilon=1.0
    )
    
    client = RetailCoFlowerClient(config)
    
    # Create dummy data for testing
    import pandas as pd
    from datetime import date, timedelta
    
    dates = [date(2023, 1, 2) + timedelta(weeks=i) for i in range(52)]
    dummy_sales = pd.DataFrame({
        'sku_id': ['SKU-0001'] * 52,
        'store_id': ['STORE-A'] * 52,
        'week_start': dates,
        'units': np.random.poisson(100, 52),
        'revenue': np.random.uniform(500, 1500, 52),
        'price': [10.0] * 52,
        'promo_flag': np.random.choice([True, False], 52, p=[0.2, 0.8])
    })
    
    client.load_data(dummy_sales)
    
    print("Client created successfully")
    print(f"Training samples: {len(client._train_loader.dataset)}")
    print(f"Model parameters: {client.federated_model.model.get_num_parameters():,}")
