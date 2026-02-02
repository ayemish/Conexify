/**
 * Self-Supervised Learning (SSL) Types
 * 
 * Defines pretraining, SSL methods, and label efficiency tracking.
 * Addresses research area B: SSL for time series to reduce dependence on labeled failures.
 */

// =============================================================================
// SSL METHOD TYPES
// =============================================================================

export type SSLMethod = 
  | 'masked_modeling'         // Masked time series modeling
  | 'contrastive'             // Contrastive learning (SimCLR, MoCo style)
  | 'predictive'              // Next-step/multi-step prediction
  | 'denoising'               // Denoising autoencoder
  | 'reconstruction'          // Full sequence reconstruction
  | 'temporal_contrast'       // TS2Vec, TNC style temporal contrast
  | 'hierarchical'            // Multi-scale representation learning
  | 'multimodal';             // Cross-sensor/modality pretraining

export type PretrainingDataSource = 
  | 'unlabeled_telemetry'     // Raw sensor data without labels
  | 'normal_operation'        // Known-good operation periods
  | 'cross_asset'             // Data from similar asset types
  | 'cross_site'              // Data from multiple sites
  | 'external_dataset'        // Public/third-party datasets
  | 'synthetic';              // Synthetically generated data

// =============================================================================
// PRETRAINING CONFIGURATION
// =============================================================================

export interface PretrainingConfig {
  config_id: string;
  config_name: string;
  description: string;
  
  // SSL method
  ssl_method: SSLMethod;
  method_params: {
    // Masked modeling params
    mask_ratio?: number;
    mask_strategy?: 'random' | 'block' | 'sensor';
    
    // Contrastive params
    temperature?: number;
    augmentation_types?: string[];
    
    // Predictive params
    prediction_horizon?: number;
    multi_step?: boolean;
  };
  
  // Pretraining data
  data_config: {
    sources: PretrainingDataSource[];
    total_samples: number;
    total_hours: number;
    
    data_filters: {
      min_quality_score?: number;
      exclude_anomalous?: boolean;
      asset_types?: string[];
      date_range?: { start: string; end: string };
    };
  };
  
  // Model architecture for pretraining
  encoder_config: {
    architecture: 'transformer' | 'cnn' | 'rnn' | 'hybrid';
    hidden_dim: number;
    n_layers: number;
    representation_dim: number;
  };
  
  // Training config
  training_config: {
    epochs: number;
    batch_size: number;
    learning_rate: number;
    optimizer: string;
    early_stopping: boolean;
  };
}

export interface PretrainedModel {
  pretrained_id: string;
  config_id: string;
  model_name: string;
  version: string;
  
  // Training metadata
  training_metadata: {
    started_at: string;
    completed_at: string;
    total_epochs_trained: number;
    final_pretraining_loss: number;
    
    compute_used: {
      gpu_hours: number;
      gpu_type: string;
    };
  };
  
  // Pretraining quality metrics
  quality_metrics: {
    reconstruction_loss?: number;
    contrastive_accuracy?: number;
    representation_quality: {
      uniformity: number;      // How well spread in representation space
      alignment: number;       // How well similar samples cluster
    };
  };
  
  // Downstream task performance (when fine-tuned)
  downstream_performance: Array<{
    task: 'anomaly_detection' | 'failure_prediction' | 'rul_estimation';
    fine_tuning_samples: number;
    performance_metrics: Record<string, number>;
    vs_from_scratch: {
      metric: string;
      pretrained_value: number;
      from_scratch_value: number;
      improvement_percent: number;
    };
  }>;
  
  // Status
  status: 'training' | 'available' | 'deprecated';
  artifact_path: string;
}

// =============================================================================
// LABEL EFFICIENCY TRACKING
// =============================================================================

export interface LabelEfficiencyAnalysis {
  analysis_id: string;
  pretrained_model_id: string;
  task: 'anomaly_detection' | 'failure_prediction' | 'rul_estimation';
  
  // Learning curves
  learning_curves: {
    // Performance at different label counts
    data_points: Array<{
      n_labeled_samples: number;
      n_failure_examples: number;
      
      // With pretraining
      pretrained_performance: {
        accuracy?: number;
        f1?: number;
        auc_roc?: number;
        recall?: number;
      };
      
      // Without pretraining (from scratch)
      from_scratch_performance: {
        accuracy?: number;
        f1?: number;
        auc_roc?: number;
        recall?: number;
      };
    }>;
    
    // Key insights
    insights: {
      samples_to_match_from_scratch: number;  // How many labeled samples with SSL to match no-SSL at full data
      label_efficiency_multiplier: number;     // e.g., 5x = need 5x fewer labels
      minimum_viable_labels: number;           // Smallest label set for acceptable performance
    };
  };
  
  // Few-shot performance
  few_shot_performance: {
    k_shot_values: number[];  // e.g., [1, 5, 10, 50]
    results: Array<{
      k: number;
      pretrained_f1: number;
      from_scratch_f1: number;
      improvement: number;
    }>;
  };
}

// =============================================================================
// TRANSFER LEARNING
// =============================================================================

export interface TransferLearningConfig {
  config_id: string;
  source_model_id: string;
  target_task: string;
  
  // What to transfer
  transfer_strategy: {
    freeze_encoder: boolean;
    freeze_layers?: number[];
    adapter_config?: {
      use_adapters: boolean;
      adapter_dim: number;
      adapter_positions: string[];
    };
  };
  
  // Fine-tuning config
  fine_tuning: {
    learning_rate: number;
    epochs: number;
    warm_up_epochs: number;
    labeled_samples: number;
  };
  
  // Target data
  target_data: {
    asset_types: string[];
    n_samples: number;
    n_failures: number;
    label_quality: 'verified' | 'inferred' | 'weak';
  };
}

export interface TransferLearningResult {
  result_id: string;
  config_id: string;
  
  // Training outcome
  training_outcome: {
    epochs_completed: number;
    final_loss: number;
    convergence_epoch: number;
  };
  
  // Performance
  performance: {
    target_task_metrics: Record<string, number>;
    
    vs_from_scratch: {
      metric: string;
      improvement_percent: number;
      training_time_reduction_percent: number;
    };
    
    vs_source_domain: {
      domain_shift_detected: boolean;
      performance_drop_percent: number;
    };
  };
  
  // Generalization
  generalization: {
    train_performance: number;
    val_performance: number;
    test_performance: number;
    overfitting_detected: boolean;
  };
}

// =============================================================================
// FOUNDATION MODEL REGISTRY
// =============================================================================

export interface FoundationModel {
  foundation_id: string;
  model_name: string;
  version: string;
  description: string;
  
  // Origin
  origin: {
    source: 'internal' | 'external' | 'public';
    provider?: string;
    original_task?: string;
    paper_reference?: string;
  };
  
  // Pretraining details
  pretraining: {
    method: SSLMethod;
    data_scale: {
      n_samples: number;
      n_assets?: number;
      time_span_years?: number;
    };
    domains: string[];  // e.g., ['hvacr', 'industrial', 'energy']
  };
  
  // Architecture
  architecture: {
    type: 'transformer' | 'cnn' | 'hybrid';
    parameters: number;
    embedding_dim: number;
    max_sequence_length: number;
  };
  
  // Recommended use
  recommended_use: {
    suitable_tasks: string[];
    suitable_domains: string[];
    min_fine_tuning_samples: number;
    expected_label_efficiency: number;
  };
  
  // Status
  status: 'experimental' | 'validated' | 'production' | 'deprecated';
  validated_on: string[];
  artifact_path: string;
}

// =============================================================================
// SSL TRAINING DASHBOARD
// =============================================================================

export interface SSLTrainingDashboard {
  dashboard_id: string;
  generated_at: string;
  
  // Active pretraining jobs
  active_jobs: Array<{
    job_id: string;
    config_name: string;
    ssl_method: SSLMethod;
    progress_percent: number;
    current_loss: number;
    eta_hours: number;
  }>;
  
  // Available pretrained models
  available_models: Array<{
    model_id: string;
    model_name: string;
    ssl_method: SSLMethod;
    pretraining_data_hours: number;
    downstream_tasks_validated: number;
    avg_label_efficiency_gain: number;
  }>;
  
  // Label efficiency summary
  label_efficiency_summary: {
    avg_efficiency_multiplier: number;
    best_performing_method: SSLMethod;
    total_labels_saved: number;
  };
  
  // Recommendations
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low';
    recommendation: string;
    expected_impact: string;
  }>;
}
