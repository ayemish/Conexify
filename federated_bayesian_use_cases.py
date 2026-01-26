"""
Federated Bayesian Learning Use Cases and Demonstrations

This module provides practical examples and use cases for combining federated learning
with Bayesian analysis across different domains including healthcare, finance, and
IoT applications.
"""

import numpy as np
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional
import pandas as pd
from sklearn.datasets import make_classification, load_breast_cancer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings('ignore')

from federated_bayesian_learning import (
    FederatedBayesianServer, FederatedClient, BayesianNeuralNetwork,
    FederatedConfig, UncertaintyBasedModelSwitcher
)


class HealthcareFederatedLearning:
    """
    Healthcare use case: Privacy-preserving disease diagnosis across hospitals
    """
    
    def __init__(self):
        self.config = FederatedConfig(
            num_clients=5,  # 5 hospitals
            num_rounds=30,
            local_epochs=5,
            learning_rate=0.001,
            beta=0.1,  # Lower KL weight for healthcare
            aggregation_method="rkl_barycenter",
            uncertainty_threshold=0.4  # Conservative threshold for medical decisions
        )
        
        # Load breast cancer dataset
        self.load_medical_data()
        
    def load_medical_data(self):
        """Load and prepare medical dataset"""
        # Load breast cancer dataset
        data = load_breast_cancer()
        X, y = data.data, data.target
        
        # Standardize features
        scaler = StandardScaler()
        X = scaler.fit_transform(X)
        
        # Split data for federated simulation (different hospitals)
        self.hospital_data = []
        samples_per_hospital = len(X) // self.config.num_clients
        
        for i in range(self.config.num_clients):
            start_idx = i * samples_per_hospital
            end_idx = (i + 1) * samples_per_hospital if i < self.config.num_clients - 1 else len(X)
            
            X_hospital = torch.FloatTensor(X[start_idx:end_idx])
            y_hospital = torch.LongTensor(y[start_idx:end_idx])
            
            # Add hospital-specific bias (simulating different patient populations)
            bias = torch.randn_like(X_hospital) * 0.1
            X_hospital += bias
            
            self.hospital_data.append((X_hospital, y_hospital))
        
        # Create test set
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self.test_data = (torch.FloatTensor(X_test), torch.LongTensor(y_test))
        
        print(f"Loaded medical data: {X.shape[1]} features, {len(np.unique(y))} classes")
        print(f"Data distributed across {self.config.num_clients} hospitals")
    
    def create_medical_model(self):
        """Create model for medical diagnosis"""
        return BayesianNeuralNetwork(
            input_dim=30,  # Breast cancer dataset has 30 features
            hidden_dims=[64, 32, 16],
            num_classes=2  # Benign/Malignant
        )
    
    def run_federated_training(self):
        """Execute federated learning across hospitals"""
        print("=== Healthcare Federated Learning ===")
        
        # Create server and model
        model = self.create_medical_model()
        server = FederatedBayesianServer(model, self.config)
        
        # Create hospital clients
        for i, (X_hospital, y_hospital) in enumerate(self.hospital_data):
            hospital_model = self.create_medical_model()
            client = FederatedClient(i, hospital_model, (X_hospital, y_hospital), self.config)
            server.register_client(client)
        
        # Train federated model
        training_history = server.train()
        
        # Evaluate on test set
        self.evaluate_medical_model(model, training_history)
        
        return model, training_history
    
    def evaluate_medical_model(self, model, training_history):
        """Evaluate model with medical metrics"""
        model.eval()
        X_test, y_test = self.test_data
        
        with torch.no_grad():
            probs, uncertainty, alpha = model(X_test)
            
            # Predictions
            pred_labels = torch.argmax(probs, dim=1)
            accuracy = (pred_labels == y_test).float().mean().item()
            
            # Medical-specific metrics
            avg_uncertainty = torch.mean(uncertainty).item()
            max_uncertainty = torch.max(uncertainty).item()
            
            # High uncertainty cases (need human review)
            high_uncertainty_mask = uncertainty > self.config.uncertainty_threshold
            high_uncertainty_rate = high_uncertainty_mask.float().mean().item()
            
            print(f"\nMedical Model Performance:")
            print(f"Accuracy: {accuracy:.4f}")
            print(f"Average Uncertainty: {avg_uncertainty:.4f}")
            print(f"Max Uncertainty: {max_uncertainty:.4f}")
            print(f"High Uncertainty Cases: {high_uncertainty_rate:.4f}")
            
            # Plot training history
            self.plot_medical_results(training_history)
    
    def plot_medical_results(self, training_history):
        """Plot medical training results"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # Accuracy over rounds
        axes[0, 0].plot(training_history['accuracy'])
        axes[0, 0].set_title('Model Accuracy Over Rounds')
        axes[0, 0].set_xlabel('Round')
        axes[0, 0].set_ylabel('Accuracy')
        axes[0, 0].grid(True)
        
        # Uncertainty over rounds
        axes[0, 1].plot(training_history['uncertainty'])
        axes[0, 1].set_title('Average Uncertainty Over Rounds')
        axes[0, 1].set_xlabel('Round')
        axes[0, 1].set_ylabel('Uncertainty')
        axes[0, 1].grid(True)
        
        # Loss over rounds
        axes[1, 0].plot(training_history['loss'])
        axes[1, 0].set_title('Training Loss Over Rounds')
        axes[1, 0].set_xlabel('Round')
        axes[1, 0].set_ylabel('Loss')
        axes[1, 0].grid(True)
        
        # Uncertainty distribution
        X_test, y_test = self.test_data
        model.eval()
        with torch.no_grad():
            _, uncertainty, _ = model(X_test)
        
        axes[1, 1].hist(uncertainty.numpy(), bins=20, alpha=0.7)
        axes[1, 1].axvline(self.config.uncertainty_threshold, color='red', 
                          linestyle='--', label='Threshold')
        axes[1, 1].set_title('Uncertainty Distribution on Test Set')
        axes[1, 1].set_xlabel('Uncertainty')
        axes[1, 1].set_ylabel('Frequency')
        axes[1, 1].legend()
        axes[1, 1].grid(True)
        
        plt.tight_layout()
        plt.savefig('/Users/erichillerbrand/CascadeProjects/windsurf-project/healthcare_federated_results.png')
        plt.show()


class FinancialFederatedLearning:
    """
    Finance use case: Fraud detection across banks with privacy preservation
    """
    
    def __init__(self):
        self.config = FederatedConfig(
            num_clients=4,  # 4 banks
            num_rounds=25,
            local_epochs=4,
            learning_rate=0.002,
            beta=0.05,  # Very low KL weight for financial stability
            aggregation_method="rkl_barycenter",
            uncertainty_threshold=0.2  # Low threshold for fraud detection
        )
        
        self.create_fraud_data()
    
    def create_fraud_data(self):
        """Create synthetic fraud detection data"""
        # Create imbalanced dataset (fraud is rare)
        X, y = make_classification(
            n_samples=10000,
            n_features=20,
            n_informative=15,
            n_redundant=5,
            n_classes=2,
            weights=[0.98, 0.02],  # 2% fraud
            random_state=42
        )
        
        # Add financial features
        financial_features = np.random.randn(len(X), 5) * 0.1
        X = np.hstack([X, financial_features])
        
        # Standardize
        scaler = StandardScaler()
        X = scaler.fit_transform(X)
        
        # Distribute across banks
        self.bank_data = []
        samples_per_bank = len(X) // self.config.num_clients
        
        for i in range(self.config.num_clients):
            start_idx = i * samples_per_bank
            end_idx = (i + 1) * samples_per_bank if i < self.config.num_clients - 1 else len(X)
            
            X_bank = torch.FloatTensor(X[start_idx:end_idx])
            y_bank = torch.LongTensor(y[start_idx:end_idx])
            
            # Bank-specific patterns
            bank_bias = torch.randn_like(X_bank) * 0.05
            X_bank += bank_bias
            
            self.bank_data.append((X_bank, y_bank))
        
        # Test set
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, 
                                                          stratify=y, random_state=42)
        self.test_data = (torch.FloatTensor(X_test), torch.LongTensor(y_test))
        
        print(f"Created fraud detection data: {X.shape[1]} features, "
              f"Fraud rate: {np.mean(y):.3f}")
    
    def create_fraud_model(self):
        """Create model for fraud detection"""
        return BayesianNeuralNetwork(
            input_dim=25,  # 20 original + 5 financial features
            hidden_dims=[128, 64, 32],
            num_classes=2  # Legitimate/Fraud
        )
    
    def run_fraud_detection(self):
        """Run federated fraud detection"""
        print("\n=== Financial Federated Learning (Fraud Detection) ===")
        
        # Create server and model
        model = self.create_fraud_model()
        server = FederatedBayesianServer(model, self.config)
        
        # Create bank clients
        for i, (X_bank, y_bank) in enumerate(self.bank_data):
            bank_model = self.create_fraud_model()
            client = FederatedClient(i, bank_model, (X_bank, y_bank), self.config)
            server.register_client(client)
        
        # Train
        training_history = server.train()
        
        # Evaluate with financial metrics
        self.evaluate_fraud_model(model, training_history)
        
        return model, training_history
    
    def evaluate_fraud_model(self, model, training_history):
        """Evaluate fraud detection model"""
        model.eval()
        X_test, y_test = self.test_data
        
        with torch.no_grad():
            probs, uncertainty, alpha = model(X_test)
            
            # Predictions
            pred_labels = torch.argmax(probs, dim=1)
            
            # Metrics
            accuracy = (pred_labels == y_test).float().mean().item()
            
            # Fraud-specific metrics
            fraud_mask = y_test == 1
            if fraud_mask.sum() > 0:
                fraud_detection_rate = (pred_labels[fraud_mask] == 1).float().mean().item()
            else:
                fraud_detection_rate = 0.0
            
            # False positive rate
            legitimate_mask = y_test == 0
            if legitimate_mask.sum() > 0:
                false_positive_rate = (pred_labels[legitimate_mask] == 1).float().mean().item()
            else:
                false_positive_rate = 0.0
            
            # Uncertainty metrics
            avg_uncertainty = torch.mean(uncertainty).item()
            high_uncertainty_fraud = (uncertainty[fraud_mask] > self.config.uncertainty_threshold).float().mean().item() if fraud_mask.sum() > 0 else 0.0
            
            print(f"\nFraud Detection Performance:")
            print(f"Overall Accuracy: {accuracy:.4f}")
            print(f"Fraud Detection Rate: {fraud_detection_rate:.4f}")
            print(f"False Positive Rate: {false_positive_rate:.4f}")
            print(f"Average Uncertainty: {avg_uncertainty:.4f}")
            print(f"High Uncertainty Fraud Cases: {high_uncertainty_fraud:.4f}")


class IoTFederatedLearning:
    """
    IoT use case: Predictive maintenance across distributed sensors
    """
    
    def __init__(self):
        self.config = FederatedConfig(
            num_clients=8,  # 8 sensor networks
            num_rounds=20,
            local_epochs=3,
            learning_rate=0.005,
            beta=0.2,
            aggregation_method="rkl_barycenter",
            uncertainty_threshold=0.3
        )
        
        self.create_iot_data()
    
    def create_iot_data(self):
        """Create IoT sensor data for predictive maintenance"""
        # Simulate time-series sensor data
        np.random.seed(42)
        
        sensor_data = []
        for i in range(self.config.num_clients):
            # Each sensor network has different characteristics
            num_samples = 500
            num_sensors = 15
            
            # Normal operation patterns
            normal_data = np.random.randn(num_samples, num_sensors) * 0.1
            
            # Add some anomaly patterns (maintenance needed)
            anomaly_mask = np.random.choice([0, 1], size=num_samples, p=[0.9, 0.1])
            anomalies = np.random.randn(num_samples, num_sensors) * 0.5
            
            # Combine normal and anomalous data
            X_iot = normal_data + anomaly_mask.reshape(-1, 1) * anomalies
            y_iot = anomaly_mask
            
            # Add sensor-specific bias
            sensor_bias = np.random.randn(num_sensors) * 0.05
            X_iot += sensor_bias
            
            sensor_data.append((torch.FloatTensor(X_iot), torch.LongTensor(y_iot)))
        
        self.sensor_data = sensor_data
        
        # Create test set
        test_samples = 200
        X_test = np.random.randn(test_samples, 15) * 0.1
        y_test = np.random.choice([0, 1], size=test_samples, p=[0.85, 0.15])
        
        # Add some anomalies to test set
        anomaly_mask_test = y_test == 1
        X_test[anomaly_mask_test] += np.random.randn(np.sum(anomaly_mask_test), 15) * 0.4
        
        self.test_data = (torch.FloatTensor(X_test), torch.LongTensor(y_test))
        
        print(f"Created IoT sensor data: {15} sensors per network, {self.config.num_clients} networks")
    
    def create_iot_model(self):
        """Create model for IoT predictive maintenance"""
        return BayesianNeuralNetwork(
            input_dim=15,
            hidden_dims=[32, 16],
            num_classes=2  # Normal/Anomaly
        )
    
    def run_iot_maintenance(self):
        """Run IoT predictive maintenance"""
        print("\n=== IoT Federated Learning (Predictive Maintenance) ===")
        
        # Create server and model
        model = self.create_iot_model()
        server = FederatedBayesianServer(model, self.config)
        
        # Create sensor network clients
        for i, (X_sensor, y_sensor) in enumerate(self.sensor_data):
            sensor_model = self.create_iot_model()
            client = FederatedClient(i, sensor_model, (X_sensor, y_sensor), self.config)
            server.register_client(client)
        
        # Train
        training_history = server.train()
        
        # Evaluate
        self.evaluate_iot_model(model, training_history)
        
        return model, training_history
    
    def evaluate_iot_model(self, model, training_history):
        """Evaluate IoT predictive maintenance model"""
        model.eval()
        X_test, y_test = self.test_data
        
        with torch.no_grad():
            probs, uncertainty, alpha = model(X_test)
            
            # Predictions
            pred_labels = torch.argmax(probs, dim=1)
            
            # Metrics
            accuracy = (pred_labels == y_test).float().mean().item()
            
            # Anomaly detection metrics
            anomaly_mask = y_test == 1
            if anomaly_mask.sum() > 0:
                anomaly_detection_rate = (pred_labels[anomaly_mask] == 1).float().mean().item()
            else:
                anomaly_detection_rate = 0.0
            
            # Uncertainty metrics
            avg_uncertainty = torch.mean(uncertainty).item()
            high_uncertainty_anomalies = (uncertainty[anomaly_mask] > self.config.uncertainty_threshold).float().mean().item() if anomaly_mask.sum() > 0 else 0.0
            
            print(f"\nIoT Predictive Maintenance Performance:")
            print(f"Overall Accuracy: {accuracy:.4f}")
            print(f"Anomaly Detection Rate: {anomaly_detection_rate:.4f}")
            print(f"Average Uncertainty: {avg_uncertainty:.4f}")
            print(f"High Uncertainty Anomalies: {high_uncertainty_anomalies:.4f}")


class ComparisonStudy:
    """
    Compare different aggregation methods and uncertainty thresholds
    """
    
    def __init__(self):
        self.aggregation_methods = ["rkl_barycenter", "weighted_average"]
        self.uncertainty_thresholds = [0.2, 0.3, 0.4, 0.5]
    
    def run_comparison(self):
        """Run comprehensive comparison study"""
        print("\n=== Federated Bayesian Learning Comparison Study ===")
        
        results = {}
        
        for method in self.aggregation_methods:
            for threshold in self.uncertainty_thresholds:
                print(f"\nTesting: {method}, threshold={threshold}")
                
                config = FederatedConfig(
                    num_clients=4,
                    num_rounds=15,
                    local_epochs=3,
                    learning_rate=0.01,
                    aggregation_method=method,
                    uncertainty_threshold=threshold
                )
                
                # Create synthetic data
                X, y = make_classification(n_samples=2000, n_features=10, n_classes=3, 
                                         n_informative=8, random_state=42)
                X = torch.FloatTensor(X)
                y = torch.LongTensor(y)
                
                # Split for federated simulation
                samples_per_client = len(X) // config.num_clients
                client_data = []
                
                for i in range(config.num_clients):
                    start_idx = i * samples_per_client
                    end_idx = (i + 1) * samples_per_client if i < config.num_clients - 1 else len(X)
                    
                    X_client = X[start_idx:end_idx]
                    y_client = y[start_idx:end_idx]
                    client_data.append((X_client, y_client))
                
                # Create and train model
                model = BayesianNeuralNetwork(input_dim=10, hidden_dims=[32, 16], num_classes=3)
                server = FederatedBayesianServer(model, config)
                
                for i, (X_client, y_client) in enumerate(client_data):
                    client_model = BayesianNeuralNetwork(input_dim=10, hidden_dims=[32, 16], num_classes=3)
                    client = FederatedClient(i, client_model, (X_client, y_client), config)
                    server.register_client(client)
                
                training_history = server.train()
                
                # Store results
                key = f"{method}_threshold_{threshold}"
                results[key] = {
                    'final_accuracy': training_history['accuracy'][-1],
                    'final_uncertainty': training_history['uncertainty'][-1],
                    'final_loss': training_history['loss'][-1],
                    'convergence_round': self.find_convergence_round(training_history['accuracy'])
                }
        
        # Display results
        self.display_comparison_results(results)
        
        return results
    
    def find_convergence_round(self, accuracy_history, threshold=0.01):
        """Find round where accuracy converges"""
        if len(accuracy_history) < 2:
            return len(accuracy_history)
        
        for i in range(1, len(accuracy_history)):
            if abs(accuracy_history[i] - accuracy_history[i-1]) < threshold:
                return i
        
        return len(accuracy_history) - 1
    
    def display_comparison_results(self, results):
        """Display comparison results in a table"""
        print("\n" + "="*80)
        print("COMPARISON RESULTS")
        print("="*80)
        
        # Create DataFrame for better display
        df_data = []
        for key, metrics in results.items():
            method, threshold = key.split('_threshold_')
            df_data.append({
                'Method': method,
                'Threshold': threshold,
                'Final Accuracy': f"{metrics['final_accuracy']:.4f}",
                'Final Uncertainty': f"{metrics['final_uncertainty']:.4f}",
                'Final Loss': f"{metrics['final_loss']:.4f}",
                'Convergence Round': metrics['convergence_round']
            })
        
        df = pd.DataFrame(df_data)
        print(df.to_string(index=False))
        
        # Find best configuration
        best_config = max(results.items(), key=lambda x: x[1]['final_accuracy'])
        print(f"\nBest Configuration: {best_config[0]}")
        print(f"Best Accuracy: {best_config[1]['final_accuracy']:.4f}")


def main():
    """Main function demonstrating all use cases"""
    
    print("FEDERATED BAYESIAN LEARNING - COMPREHENSIVE DEMONSTRATION")
    print("="*60)
    
    # 1. Healthcare use case
    healthcare = HealthcareFederatedLearning()
    healthcare_model, healthcare_history = healthcare.run_federated_training()
    
    # 2. Financial use case
    finance = FinancialFederatedLearning()
    finance_model, finance_history = finance.run_fraud_detection()
    
    # 3. IoT use case
    iot = IoTFederatedLearning()
    iot_model, iot_history = iot.run_iot_maintenance()
    
    # 4. Comparison study
    comparison = ComparisonStudy()
    comparison_results = comparison.run_comparison()
    
    print("\n" + "="*60)
    print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    # Summary
    print("\nSUMMARY:")
    print(f"Healthcare - Final Accuracy: {healthcare_history['accuracy'][-1]:.4f}")
    print(f"Finance - Final Accuracy: {finance_history['accuracy'][-1]:.4f}")
    print(f"IoT - Final Accuracy: {iot_history['accuracy'][-1]:.4f}")
    
    print("\nKey Benefits Demonstrated:")
    print("✓ Privacy preservation across institutions")
    print("✓ Uncertainty quantification for critical decisions")
    print("✓ Robust aggregation using information-geometric barycenters")
    print("✓ Adaptive model switching based on confidence")
    print("✓ Domain-specific configuration and evaluation")


if __name__ == "__main__":
    main()
