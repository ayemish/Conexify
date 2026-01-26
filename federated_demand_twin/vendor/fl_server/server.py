"""
Federated Learning Server (Coordinator) for Demand Forecasting

FR-2.1: Federated coordinator that initiates rounds, receives client updates,
aggregates them, and publishes a global model version.

FR-2.3: Complete 10-30 training rounds and produce versioned global model artifact.

FR-2.4: Support configuration toggles for secure aggregation and differential privacy.

Implements Flower server with FedAvg aggregation and model versioning.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import hashlib
import logging
import pickle

# Flower imports
try:
    import flwr as fl
    from flwr.common import (
        Metrics, Parameters, Scalar,
        ndarrays_to_parameters, parameters_to_ndarrays,
        FitRes, EvaluateRes
    )
    from flwr.server.strategy import FedAvg
    from flwr.server.client_proxy import ClientProxy
    FLOWER_AVAILABLE = True
except ImportError:
    FLOWER_AVAILABLE = False
    logging.warning("Flower not installed. Using mock server.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuration for federated learning server"""
    # Server settings
    server_address: str = "0.0.0.0:8080"
    num_rounds: int = 20  # FR-2.3: 10-30 rounds
    min_fit_clients: int = 1
    min_evaluate_clients: int = 1
    min_available_clients: int = 1
    
    # Aggregation settings
    fraction_fit: float = 1.0  # Fraction of clients for training
    fraction_evaluate: float = 1.0  # Fraction for evaluation
    
    # Privacy settings (FR-2.4)
    enable_secure_aggregation: bool = False
    enable_differential_privacy: bool = False
    dp_noise_multiplier: float = 1.0
    dp_clipping_bound: float = 1.0
    
    # Model versioning
    model_registry_path: str = "./models/registry"
    version_prefix: str = "demand-forecast"
    
    # Logging
    metrics_path: str = "./logs/server_metrics.json"
    save_checkpoints: bool = True
    checkpoint_interval: int = 5


@dataclass
class ModelVersion:
    """Model version metadata"""
    version: str
    round_id: int
    config_hash: str
    num_clients: int
    aggregation_method: str
    privacy_flags: Dict[str, bool]
    metrics: Dict[str, float]
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'version': self.version,
            'round_id': self.round_id,
            'config_hash': self.config_hash,
            'num_clients': self.num_clients,
            'aggregation_method': self.aggregation_method,
            'privacy_flags': self.privacy_flags,
            'metrics': self.metrics,
            'created_at': self.created_at
        }


class ModelRegistry:
    """
    Registry for managing versioned global models.
    
    FR-2.3: Produce versioned global model artifact
    """
    
    def __init__(self, registry_path: str, version_prefix: str = "demand-forecast"):
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.version_prefix = version_prefix
        
        # Load existing versions
        self.versions: Dict[str, ModelVersion] = {}
        self._load_registry()
    
    def _load_registry(self):
        """Load existing model versions from registry"""
        index_path = self.registry_path / "index.json"
        if index_path.exists():
            with open(index_path) as f:
                index = json.load(f)
                for v in index.get('versions', []):
                    self.versions[v['version']] = ModelVersion(**v)
    
    def _save_registry(self):
        """Save registry index"""
        index_path = self.registry_path / "index.json"
        with open(index_path, 'w') as f:
            json.dump({
                'versions': [v.to_dict() for v in self.versions.values()],
                'latest': self.get_latest_version()
            }, f, indent=2)
    
    def generate_version(self, round_id: int) -> str:
        """Generate semantic version string"""
        # Format: prefix-vMAJOR.MINOR.PATCH (round-based)
        major = round_id // 100
        minor = (round_id % 100) // 10
        patch = round_id % 10
        return f"{self.version_prefix}-v{major}.{minor}.{patch}"
    
    def save_model(
        self,
        parameters: List[np.ndarray],
        round_id: int,
        config_hash: str,
        num_clients: int,
        metrics: Dict[str, float],
        privacy_flags: Dict[str, bool]
    ) -> str:
        """Save model to registry and return version"""
        version = self.generate_version(round_id)
        
        # Save parameters
        model_path = self.registry_path / f"{version}.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(parameters, f)
        
        # Create version metadata
        model_version = ModelVersion(
            version=version,
            round_id=round_id,
            config_hash=config_hash,
            num_clients=num_clients,
            aggregation_method="fedavg",
            privacy_flags=privacy_flags,
            metrics=metrics
        )
        
        self.versions[version] = model_version
        self._save_registry()
        
        logger.info(f"Saved model version {version} to registry")
        return version
    
    def load_model(self, version: str) -> Optional[List[np.ndarray]]:
        """Load model parameters by version"""
        model_path = self.registry_path / f"{version}.pkl"
        if not model_path.exists():
            return None
        
        with open(model_path, 'rb') as f:
            return pickle.load(f)
    
    def get_latest_version(self) -> Optional[str]:
        """Get latest model version"""
        if not self.versions:
            return None
        return max(self.versions.keys(), key=lambda v: self.versions[v].round_id)
    
    def get_version_info(self, version: str) -> Optional[ModelVersion]:
        """Get version metadata"""
        return self.versions.get(version)


def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    """Weighted average of metrics from multiple clients"""
    if not metrics:
        return {}
    
    # Get all metric keys
    all_keys = set()
    for _, m in metrics:
        all_keys.update(m.keys())
    
    aggregated = {}
    total_samples = sum(num for num, _ in metrics)
    
    for key in all_keys:
        weighted_sum = sum(
            num * m.get(key, 0) for num, m in metrics
        )
        aggregated[key] = weighted_sum / total_samples if total_samples > 0 else 0
    
    return aggregated


class FederatedDemandStrategy:
    """
    Custom federated learning strategy for demand forecasting.
    
    Extends FedAvg with:
    - Model versioning and registry
    - Privacy controls logging
    - Detailed metrics aggregation
    """
    
    def __init__(
        self,
        config: ServerConfig,
        initial_parameters: Optional[List[np.ndarray]] = None
    ):
        self.config = config
        self.registry = ModelRegistry(
            config.model_registry_path,
            config.version_prefix
        )
        
        self.current_round = 0
        self.round_metrics: List[Dict[str, Any]] = []
        
        # Config hash for reproducibility
        self.config_hash = self._compute_config_hash()
        
        # Store initial parameters
        self.initial_parameters = initial_parameters
    
    def _compute_config_hash(self) -> str:
        """Compute hash of configuration"""
        config_dict = {
            'num_rounds': self.config.num_rounds,
            'fraction_fit': self.config.fraction_fit,
            'enable_secure_aggregation': self.config.enable_secure_aggregation,
            'enable_differential_privacy': self.config.enable_differential_privacy,
        }
        return hashlib.md5(
            json.dumps(config_dict, sort_keys=True).encode()
        ).hexdigest()[:8]
    
    def aggregate_fit(
        self,
        server_round: int,
        results: List[Tuple[Any, Any]],
        failures: List[Any]
    ) -> Tuple[Optional[List[np.ndarray]], Dict[str, Scalar]]:
        """
        Aggregate model updates from clients.
        
        FR-2.1: Aggregate client updates
        """
        if not results:
            return None, {}
        
        self.current_round = server_round
        
        # Extract parameters and metrics
        weights_results = []
        metrics_list = []
        
        for client_proxy, fit_res in results:
            parameters = parameters_to_ndarrays(fit_res.parameters)
            num_examples = fit_res.num_examples
            metrics = fit_res.metrics
            
            weights_results.append((parameters, num_examples))
            metrics_list.append((num_examples, metrics))
        
        # FedAvg aggregation
        aggregated_params = self._fedavg_aggregate(weights_results)
        
        # Apply DP noise if enabled
        if self.config.enable_differential_privacy:
            aggregated_params = self._apply_dp_noise(aggregated_params)
        
        # Aggregate metrics
        aggregated_metrics = weighted_average(metrics_list)
        
        # Save to registry at checkpoints
        if (self.config.save_checkpoints and 
            server_round % self.config.checkpoint_interval == 0):
            
            privacy_flags = {
                'secure_aggregation': self.config.enable_secure_aggregation,
                'differential_privacy': self.config.enable_differential_privacy
            }
            
            version = self.registry.save_model(
                parameters=aggregated_params,
                round_id=server_round,
                config_hash=self.config_hash,
                num_clients=len(results),
                metrics=aggregated_metrics,
                privacy_flags=privacy_flags
            )
            aggregated_metrics['model_version'] = version
        
        # Log round metrics
        self._log_round(server_round, len(results), aggregated_metrics, len(failures))
        
        logger.info(
            f"Round {server_round}: Aggregated {len(results)} clients, "
            f"failures: {len(failures)}, loss: {aggregated_metrics.get('loss', 'N/A')}"
        )
        
        return aggregated_params, aggregated_metrics
    
    def _fedavg_aggregate(
        self,
        results: List[Tuple[List[np.ndarray], int]]
    ) -> List[np.ndarray]:
        """FedAvg weighted aggregation"""
        # Calculate total samples
        total_samples = sum(num for _, num in results)
        
        # Weighted average of parameters
        aggregated = None
        for parameters, num_samples in results:
            weight = num_samples / total_samples
            
            if aggregated is None:
                aggregated = [p * weight for p in parameters]
            else:
                for i, p in enumerate(parameters):
                    aggregated[i] += p * weight
        
        return aggregated
    
    def _apply_dp_noise(
        self,
        parameters: List[np.ndarray]
    ) -> List[np.ndarray]:
        """Apply differential privacy noise to aggregated parameters"""
        noisy_params = []
        for param in parameters:
            noise = np.random.normal(
                0,
                self.config.dp_noise_multiplier * self.config.dp_clipping_bound,
                param.shape
            )
            noisy_params.append(param + noise.astype(param.dtype))
        
        logger.info("Applied DP noise to aggregated parameters")
        return noisy_params
    
    def _log_round(
        self,
        round_num: int,
        num_clients: int,
        metrics: Dict[str, Any],
        num_failures: int
    ):
        """Log round metrics for audit"""
        entry = {
            'round': round_num,
            'timestamp': datetime.utcnow().isoformat(),
            'num_clients': num_clients,
            'num_failures': num_failures,
            'privacy_settings': {
                'secure_aggregation_enabled': self.config.enable_secure_aggregation,
                'differential_privacy_enabled': self.config.enable_differential_privacy,
            },
            'metrics': metrics,
            'config_hash': self.config_hash
        }
        
        self.round_metrics.append(entry)
        
        # Save to file
        metrics_path = Path(self.config.metrics_path)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(metrics_path, 'w') as f:
            json.dump(self.round_metrics, f, indent=2)
    
    def get_final_model_version(self) -> Optional[str]:
        """Get the final trained model version"""
        return self.registry.get_latest_version()


if FLOWER_AVAILABLE:
    class DemandForecastFedAvg(FedAvg):
        """
        Custom FedAvg strategy with model registry integration.
        """
        
        def __init__(
            self,
            config: ServerConfig,
            initial_parameters: Optional[Parameters] = None,
            **kwargs
        ):
            self.server_config = config
            self.demand_strategy = FederatedDemandStrategy(
                config,
                parameters_to_ndarrays(initial_parameters) if initial_parameters else None
            )
            
            super().__init__(
                fraction_fit=config.fraction_fit,
                fraction_evaluate=config.fraction_evaluate,
                min_fit_clients=config.min_fit_clients,
                min_evaluate_clients=config.min_evaluate_clients,
                min_available_clients=config.min_available_clients,
                initial_parameters=initial_parameters,
                fit_metrics_aggregation_fn=weighted_average,
                evaluate_metrics_aggregation_fn=weighted_average,
                **kwargs
            )
        
        def aggregate_fit(
            self,
            server_round: int,
            results: List[Tuple[ClientProxy, FitRes]],
            failures: List[Any]
        ) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
            """Override to add model versioning"""
            
            # Use custom aggregation
            aggregated_params, metrics = self.demand_strategy.aggregate_fit(
                server_round, results, failures
            )
            
            if aggregated_params is None:
                return None, {}
            
            # Convert to Flower Parameters
            parameters = ndarrays_to_parameters(aggregated_params)
            
            return parameters, metrics


class MockFederatedServer:
    """
    Mock server for testing without Flower.
    
    Simulates federated learning rounds for development.
    """
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.strategy = FederatedDemandStrategy(config)
        self.global_parameters: Optional[List[np.ndarray]] = None
    
    def initialize(self, initial_parameters: List[np.ndarray]):
        """Set initial model parameters"""
        self.global_parameters = initial_parameters
    
    def run_round(
        self,
        client_updates: List[Tuple[List[np.ndarray], int, Dict[str, float]]]
    ) -> Tuple[List[np.ndarray], Dict[str, float]]:
        """
        Run a single federated round with provided client updates.
        
        Args:
            client_updates: List of (parameters, num_samples, metrics) from clients
        
        Returns:
            Aggregated parameters and metrics
        """
        # Convert to expected format
        results = []
        for params, num_samples, metrics in client_updates:
            # Create mock fit result
            class MockFitRes:
                def __init__(self, p, n, m):
                    self.parameters = ndarrays_to_parameters(p) if FLOWER_AVAILABLE else p
                    self.num_examples = n
                    self.metrics = m
            
            results.append((None, MockFitRes(params, num_samples, metrics)))
        
        # Aggregate
        aggregated, metrics = self.strategy.aggregate_fit(
            self.strategy.current_round + 1,
            results,
            failures=[]
        )
        
        self.global_parameters = aggregated
        return aggregated, metrics
    
    def get_global_parameters(self) -> Optional[List[np.ndarray]]:
        """Get current global model parameters"""
        return self.global_parameters
    
    def get_final_version(self) -> Optional[str]:
        """Get final model version"""
        return self.strategy.get_final_model_version()


def create_server(
    config: Optional[ServerConfig] = None,
    initial_parameters: Optional[List[np.ndarray]] = None
) -> Any:
    """
    Factory function to create federated server.
    
    Returns Flower server strategy if available, otherwise mock server.
    """
    config = config or ServerConfig()
    
    if FLOWER_AVAILABLE and initial_parameters is not None:
        parameters = ndarrays_to_parameters(initial_parameters)
        return DemandForecastFedAvg(config, initial_parameters=parameters)
    else:
        server = MockFederatedServer(config)
        if initial_parameters is not None:
            server.initialize(initial_parameters)
        return server


def start_server(
    config: Optional[ServerConfig] = None,
    initial_parameters: Optional[List[np.ndarray]] = None
):
    """
    Start the Flower server.
    
    FR-2.1: Run federated coordinator
    FR-2.3: Complete 10-30 rounds
    """
    if not FLOWER_AVAILABLE:
        raise ImportError("Flower is required. Install with: pip install flwr")
    
    config = config or ServerConfig()
    
    # Create strategy
    strategy = create_server(config, initial_parameters)
    
    logger.info(f"Starting Flower server on {config.server_address}")
    logger.info(f"Configured for {config.num_rounds} rounds")
    logger.info(f"Privacy: SecAgg={config.enable_secure_aggregation}, DP={config.enable_differential_privacy}")
    
    # Start server
    fl.server.start_server(
        server_address=config.server_address,
        config=fl.server.ServerConfig(num_rounds=config.num_rounds),
        strategy=strategy
    )
    
    # Log final model version
    final_version = strategy.demand_strategy.get_final_model_version()
    logger.info(f"Training complete. Final model version: {final_version}")
    
    return final_version


if __name__ == "__main__":
    # Test server creation
    config = ServerConfig(
        num_rounds=10,
        enable_differential_privacy=True,
        dp_noise_multiplier=0.5
    )
    
    # Create mock server for testing
    server = MockFederatedServer(config)
    
    # Initialize with dummy parameters
    dummy_params = [np.random.randn(100, 50), np.random.randn(50)]
    server.initialize(dummy_params)
    
    # Simulate a round
    client_updates = [
        (dummy_params, 1000, {'loss': 0.5}),
        (dummy_params, 800, {'loss': 0.6}),
    ]
    
    aggregated, metrics = server.run_round(client_updates)
    
    print("Mock server test complete")
    print(f"Aggregated parameters shapes: {[p.shape for p in aggregated]}")
    print(f"Metrics: {metrics}")
