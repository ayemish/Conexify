"""
Federated Bayesian Learning Architecture

This module implements a comprehensive framework for combining federated learning
with Bayesian analysis, enabling privacy-preserving machine learning with uncertainty
quantification.

Key Components:
1. Bayesian Federated Learning (BFL) with information-geometric barycenters
2. Uncertainty quantification using Dirichlet distributions
3. Personalized model switching based on confidence
4. Privacy-preserving aggregation of posterior distributions
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal, Dirichlet, kl_divergence
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FederatedConfig:
    """Configuration for federated Bayesian learning"""
    num_clients: int = 10
    num_rounds: int = 100
    local_epochs: int = 5
    learning_rate: float = 0.01
    beta: float = 1.0  # KL divergence weight
    alpha_divergence: float = 0.0  # α-divergence parameter (0 = reverse KL)
    uncertainty_threshold: float = 0.5
    privacy_budget: float = 1.0
    aggregation_method: str = "rkl_barycenter"  # Options: "rkl_barycenter", "weighted_average", "dirichlet"


class BayesianLayer(nn.Module):
    """
    Bayesian neural network layer with Gaussian weight distributions
    """
    
    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        
        # Weight parameters (mean and log variance)
        self.weight_mu = nn.Parameter(torch.Tensor(out_features, in_features))
        self.weight_logvar = nn.Parameter(torch.Tensor(out_features, in_features))
        
        # Bias parameters (mean and log variance)
        self.bias_mu = nn.Parameter(torch.Tensor(out_features))
        self.bias_logvar = nn.Parameter(torch.Tensor(out_features))
        
        self.reset_parameters()
    
    def reset_parameters(self):
        """Initialize parameters"""
        nn.init.xavier_uniform_(self.weight_mu)
        nn.init.constant_(self.weight_logvar, -3.0)  # Start with small variance
        nn.init.zeros_(self.bias_mu)
        nn.init.constant_(self.bias_logvar, -3.0)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass with weight sampling"""
        if self.training:
            # Sample weights during training
            weight_std = torch.exp(0.5 * self.weight_logvar)
            weight = self.weight_mu + weight_std * torch.randn_like(weight_std)
            
            bias_std = torch.exp(0.5 * self.bias_logvar)
            bias = self.bias_mu + bias_std * torch.randn_like(bias_std)
        else:
            # Use mean weights during inference
            weight = self.weight_mu
            bias = self.bias_mu
        
        return F.linear(x, weight, bias)
    
    def get_kl_divergence(self) -> torch.Tensor:
        """Calculate KL divergence from prior (standard normal)"""
        # KL divergence for weights
        kl_weight = 0.5 * torch.sum(
            torch.exp(self.weight_logvar) + self.weight_mu**2 - 1 - self.weight_logvar
        )
        
        # KL divergence for bias
        kl_bias = 0.5 * torch.sum(
            torch.exp(self.bias_logvar) + self.bias_mu**2 - 1 - self.bias_logvar
        )
        
        return kl_weight + kl_bias


class DirichletOutput(nn.Module):
    """
    Dirichlet output layer for uncertainty quantification
    """
    
    def __init__(self, input_dim: int, num_classes: int):
        super().__init__()
        self.num_classes = num_classes
        self.alpha_network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_classes),
            nn.Softplus()  # Ensure positive alpha parameters
        )
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns both predictive probabilities and uncertainty measures
        """
        alpha = self.alpha_network(x) + 1.0  # Ensure alpha > 1
        
        # Expected probabilities
        probs = alpha / torch.sum(alpha, dim=-1, keepdim=True)
        
        # Uncertainty measures
        total_alpha = torch.sum(alpha, dim=-1, keepdim=True)
        uncertainty = self.num_classes / total_alpha
        
        return probs, uncertainty, alpha


class BayesianNeuralNetwork(nn.Module):
    """
    Complete Bayesian neural network with uncertainty quantification
    """
    
    def __init__(self, input_dim: int, hidden_dims: List[int], num_classes: int):
        super().__init__()
        layers = []
        
        # Build hidden layers
        prev_dim = input_dim
        for hidden_dim in hidden_dims:
            layers.append(BayesianLayer(prev_dim, hidden_dim))
            layers.append(nn.ReLU())
            prev_dim = hidden_dim
        
        self.hidden_layers = nn.Sequential(*layers)
        
        # Calculate the final hidden dimension for Dirichlet output
        final_hidden_dim = hidden_dims[-1] if hidden_dims else input_dim
        self.dirichlet_output = DirichletOutput(final_hidden_dim, num_classes)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass returning predictions and uncertainties"""
        hidden = self.hidden_layers(x)
        probs, uncertainty, alpha = self.dirichlet_output(hidden)
        return probs, uncertainty, alpha
    
    def get_kl_divergence(self) -> torch.Tensor:
        """Get total KL divergence for all Bayesian layers"""
        kl_total = 0.0
        for layer in self.hidden_layers:
            if isinstance(layer, BayesianLayer):
                kl_total += layer.get_kl_divergence()
        return kl_total


class FederatedClient:
    """
    Federated learning client with Bayesian model
    """
    
    def __init__(self, client_id: int, model: BayesianNeuralNetwork, 
                 train_data: Tuple[torch.Tensor, torch.Tensor], config: FederatedConfig):
        self.client_id = client_id
        self.model = model
        self.train_data = train_data
        self.config = config
        self.optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        
        # Store posterior statistics
        self.weight_means = {}
        self.weight_variances = {}
    
    def local_training(self) -> Dict[str, torch.Tensor]:
        """Perform local training with Bayesian inference"""
        self.model.train()
        x_train, y_train = self.train_data
        
        for epoch in range(self.config.local_epochs):
            # Forward pass
            probs, uncertainty, alpha = self.model(x_train)
            
            # Loss computation
            # 1. Classification loss (negative log likelihood)
            classification_loss = F.nll_loss(torch.log(probs + 1e-8), y_train)
            
            # 2. KL divergence loss
            kl_loss = self.model.get_kl_divergence() / len(x_train)
            
            # 3. Total loss
            total_loss = classification_loss + self.config.beta * kl_loss
            
            # Backward pass
            self.optimizer.zero_grad()
            total_loss.backward()
            self.optimizer.step()
        
        # Extract posterior statistics
        self._extract_posterior_stats()
        
        return self.get_model_parameters()
    
    def _extract_posterior_stats(self):
        """Extract mean and variance from posterior distributions"""
        for name, param in self.model.named_parameters():
            if 'mu' in name:
                self.weight_means[name] = param.data.clone()
            elif 'logvar' in name:
                self.weight_variances[name] = torch.exp(param.data).clone()
    
    def get_model_parameters(self) -> Dict[str, torch.Tensor]:
        """Get model parameters for aggregation"""
        params = {}
        for name, param in self.model.named_parameters():
            params[name] = param.data.clone()
        return params
    
    def set_model_parameters(self, params: Dict[str, torch.Tensor]):
        """Set model parameters from server"""
        for name, param in self.model.named_parameters():
            if name in params:
                param.data.copy_(params[name])
    
    def evaluate_uncertainty(self, x_test: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Evaluate model with uncertainty quantification"""
        self.model.eval()
        with torch.no_grad():
            probs, uncertainty, alpha = self.model(x_test)
            return probs, uncertainty


class BarycentricAggregator:
    """
    Information-geometric barycenter aggregation for Bayesian federated learning
    """
    
    def __init__(self, config: FederatedConfig):
        self.config = config
    
    def aggregate_rkl_barycenter(self, client_params: List[Dict[str, torch.Tensor]], 
                                 client_weights: List[float]) -> Dict[str, torch.Tensor]:
        """
        Aggregate using Reverse KL barycenter
        Based on: p_RKL* = argmin_p Σ w_k * D_RKL(p_k || p)
        """
        aggregated_params = {}
        
        # Get all parameter names
        param_names = client_params[0].keys()
        
        for param_name in param_names:
            # Collect parameter tensors from all clients
            param_tensors = [params[param_name] for params in client_params]
            
            if 'mu' in param_name:
                # For mean parameters: weighted average
                aggregated_params[param_name] = sum(
                    w * p for w, p in zip(client_weights, param_tensors)
                )
            elif 'logvar' in param_name:
                # For variance parameters: harmonic mean (for RKL barycenter)
                # Convert to variance space
                variances = [torch.exp(p) for p in param_tensors]
                
                # Harmonic mean
                inv_variances = [1.0 / (v + 1e-8) for v in variances]
                weighted_inv_var = sum(w * inv for w, inv in zip(client_weights, inv_variances))
                aggregated_var = 1.0 / (weighted_inv_var + 1e-8)
                
                # Convert back to log variance
                aggregated_params[param_name] = torch.log(aggregated_var + 1e-8)
            else:
                # For other parameters: weighted average
                aggregated_params[param_name] = sum(
                    w * p for w, p in zip(client_weights, param_tensors)
                )
        
        return aggregated_params
    
    def aggregate_weighted_average(self, client_params: List[Dict[str, torch.Tensor]], 
                                  client_weights: List[float]) -> Dict[str, torch.Tensor]:
        """Standard weighted average aggregation"""
        aggregated_params = {}
        
        for param_name in client_params[0].keys():
            param_tensors = [params[param_name] for params in client_params]
            aggregated_params[param_name] = sum(
                w * p for w, p in zip(client_weights, param_tensors)
            )
        
        return aggregated_params


class FederatedBayesianServer:
    """
    Federated learning server with Bayesian aggregation
    """
    
    def __init__(self, model: BayesianNeuralNetwork, config: FederatedConfig):
        self.model = model
        self.config = config
        self.aggregator = BarycentricAggregator(config)
        self.clients = []
        
        # Training history
        self.training_history = {
            'loss': [],
            'uncertainty': [],
            'accuracy': []
        }
    
    def register_client(self, client: FederatedClient):
        """Register a federated client"""
        self.clients.append(client)
    
    def federated_round(self, round_num: int) -> Dict[str, float]:
        """Execute one round of federated learning"""
        logger.info(f"Starting federated round {round_num}")
        
        # 1. Send global model to clients
        global_params = self.get_model_parameters()
        for client in self.clients:
            client.set_model_parameters(global_params)
        
        # 2. Local training on clients
        client_params = []
        client_weights = []
        
        for client in self.clients:
            params = client.local_training()
            client_params.append(params)
            
            # Weight based on dataset size (simplified)
            data_size = len(client.train_data[0])
            client_weights.append(data_size)
        
        # Normalize weights
        total_weight = sum(client_weights)
        client_weights = [w / total_weight for w in client_weights]
        
        # 3. Aggregate client updates
        if self.config.aggregation_method == "rkl_barycenter":
            aggregated_params = self.aggregator.aggregate_rkl_barycenter(
                client_params, client_weights
            )
        else:
            aggregated_params = self.aggregator.aggregate_weighted_average(
                client_params, client_weights
            )
        
        # 4. Update global model
        self.set_model_parameters(aggregated_params)
        
        # 5. Evaluate and record metrics
        metrics = self.evaluate_global_model()
        self.training_history['loss'].append(metrics['loss'])
        self.training_history['uncertainty'].append(metrics['uncertainty'])
        self.training_history['accuracy'].append(metrics['accuracy'])
        
        logger.info(f"Round {round_num} completed. Loss: {metrics['loss']:.4f}, "
                   f"Uncertainty: {metrics['uncertainty']:.4f}, Accuracy: {metrics['accuracy']:.4f}")
        
        return metrics
    
    def get_model_parameters(self) -> Dict[str, torch.Tensor]:
        """Get current global model parameters"""
        params = {}
        for name, param in self.model.named_parameters():
            params[name] = param.data.clone()
        return params
    
    def set_model_parameters(self, params: Dict[str, torch.Tensor]):
        """Set global model parameters"""
        for name, param in self.model.named_parameters():
            if name in params:
                param.data.copy_(params[name])
    
    def evaluate_global_model(self) -> Dict[str, float]:
        """Evaluate global model performance"""
        self.model.eval()
        
        # Use first client's data for evaluation (simplified)
        if not self.clients:
            return {'loss': 0.0, 'uncertainty': 0.0, 'accuracy': 0.0}
        
        x_test, y_test = self.clients[0].train_data
        
        with torch.no_grad():
            probs, uncertainty, alpha = self.model(x_test)
            
            # Loss
            loss = F.nll_loss(torch.log(probs + 1e-8), y_test)
            
            # Average uncertainty
            avg_uncertainty = torch.mean(uncertainty).item()
            
            # Accuracy
            pred_labels = torch.argmax(probs, dim=1)
            accuracy = (pred_labels == y_test).float().mean().item()
        
        return {
            'loss': loss.item(),
            'uncertainty': avg_uncertainty,
            'accuracy': accuracy
        }
    
    def train(self) -> Dict[str, List[float]]:
        """Execute complete federated training"""
        logger.info(f"Starting federated training with {len(self.clients)} clients")
        
        for round_num in range(self.config.num_rounds):
            self.federated_round(round_num)
        
        logger.info("Federated training completed")
        return self.training_history


class UncertaintyBasedModelSwitcher:
    """
    Model switching mechanism based on uncertainty quantification
    """
    
    def __init__(self, uncertainty_threshold: float = 0.5):
        self.uncertainty_threshold = uncertainty_threshold
        self.global_model = None
        self.personal_models = {}
    
    def should_use_global_model(self, uncertainty: float) -> bool:
        """Decide whether to use global model based on uncertainty"""
        return uncertainty < self.uncertainty_threshold
    
    def predict_with_switching(self, x: torch.Tensor, client_id: int) -> torch.Tensor:
        """
        Make prediction with automatic model switching
        """
        # Get uncertainty from global model
        if self.global_model:
            self.global_model.eval()
            with torch.no_grad():
                probs, uncertainty, _ = self.global_model(x)
                avg_uncertainty = torch.mean(uncertainty).item()
        
        # Decide which model to use
        if self.should_use_global_model(avg_uncertainty):
            return probs
        elif client_id in self.personal_models:
            # Use personal model
            personal_model = self.personal_models[client_id]
            personal_model.eval()
            with torch.no_grad():
                probs, _, _ = personal_model(x)
            return probs
        else:
            # Fall back to global model
            return probs


def create_synthetic_data(num_samples: int = 1000, num_classes: int = 3, 
                         input_dim: int = 10) -> Tuple[torch.Tensor, torch.Tensor]:
    """Create synthetic federated learning data"""
    np.random.seed(42)
    
    # Generate features
    X = torch.randn(num_samples, input_dim)
    
    # Generate labels with some structure
    weights = torch.randn(input_dim, num_classes)
    logits = X @ weights + 0.5 * torch.randn(num_samples, num_classes)
    y = torch.argmax(logits, dim=1)
    
    return X, y


def main():
    """Main function demonstrating federated Bayesian learning"""
    
    # Configuration
    config = FederatedConfig(
        num_clients=5,
        num_rounds=20,
        local_epochs=3,
        learning_rate=0.01,
        beta=0.1,
        aggregation_method="rkl_barycenter",
        uncertainty_threshold=0.3
    )
    
    # Create global model
    model = BayesianNeuralNetwork(
        input_dim=10,
        hidden_dims=[64, 32],
        num_classes=3
    )
    
    # Create server
    server = FederatedBayesianServer(model, config)
    
    # Create clients with synthetic data
    for i in range(config.num_clients):
        # Create client-specific data (heterogeneous)
        client_data = create_synthetic_data(num_samples=100)
        client_model = BayesianNeuralNetwork(
            input_dim=10,
            hidden_dims=[64, 32],
            num_classes=3
        )
        
        client = FederatedClient(i, client_model, client_data, config)
        server.register_client(client)
    
    # Train federated model
    training_history = server.train()
    
    # Create uncertainty-based switcher
    switcher = UncertaintyBasedModelSwitcher(config.uncertainty_threshold)
    switcher.global_model = model
    
    # Demonstrate uncertainty-based switching
    test_data = create_synthetic_data(num_samples=50)
    x_test, y_test = test_data
    
    # Get predictions with uncertainty
    model.eval()
    with torch.no_grad():
        probs, uncertainty, alpha = model(x_test)
        
        print(f"Average uncertainty: {torch.mean(uncertainty):.4f}")
        print(f"Prediction confidence: {torch.mean(torch.max(probs, dim=1)[0]):.4f}")
        
        # Show switching decisions
        for i in range(min(10, len(x_test))):
            use_global = switcher.should_use_global_model(uncertainty[i].item())
            print(f"Sample {i}: Uncertainty={uncertainty[i].item():.4f}, "
                  f"Using {'Global' if use_global else 'Personal'} model")
    
    print("\nFederated Bayesian Learning completed successfully!")
    print(f"Final accuracy: {training_history['accuracy'][-1]:.4f}")
    print(f"Final uncertainty: {training_history['uncertainty'][-1]:.4f}")


if __name__ == "__main__":
    main()
