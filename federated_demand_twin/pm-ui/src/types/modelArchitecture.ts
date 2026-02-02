/**
 * Model Architecture Types
 * 
 * Defines model architecture metadata for transformer, RNN, and classical models.
 * Supports attention visualization and architecture-aware evaluation.
 * Addresses research area C: Transformers and attention-based architectures.
 */

// =============================================================================
// ARCHITECTURE TYPES
// =============================================================================

export type ArchitectureFamily = 
  | 'transformer'
  | 'rnn'
  | 'cnn'
  | 'mlp'
  | 'ensemble'
  | 'classical'
  | 'hybrid';

export type TransformerVariant = 
  | 'vanilla'
  | 'informer'
  | 'autoformer'
  | 'patchtst'
  | 'timesformer'
  | 'temporal_fusion_transformer';

export type RNNVariant = 
  | 'lstm'
  | 'gru'
  | 'bilstm'
  | 'attention_lstm';

export type ClassicalModel = 
  | 'random_forest'
  | 'gradient_boosting'
  | 'xgboost'
  | 'lightgbm'
  | 'isolation_forest'
  | 'svm';

// =============================================================================
// MODEL ARCHITECTURE METADATA
// =============================================================================

export interface ModelArchitecture {
  architecture_id: string;
  model_id: string;
  model_version: string;
  
  // Architecture classification
  family: ArchitectureFamily;
  variant?: TransformerVariant | RNNVariant | ClassicalModel;
  is_hybrid: boolean;
  hybrid_components?: ArchitectureFamily[];
  
  // Architecture details
  details: {
    // Common
    input_features: number;
    output_dim: number;
    total_parameters: number;
    trainable_parameters: number;
    
    // Transformer-specific
    transformer_config?: {
      n_layers: number;
      n_heads: number;
      d_model: number;
      d_ff: number;
      max_seq_length: number;
      positional_encoding: 'sinusoidal' | 'learned' | 'rotary' | 'alibi';
      attention_type: 'full' | 'sparse' | 'linear' | 'local';
    };
    
    // RNN-specific
    rnn_config?: {
      n_layers: number;
      hidden_size: number;
      bidirectional: boolean;
      dropout: number;
    };
    
    // CNN-specific
    cnn_config?: {
      n_layers: number;
      kernel_sizes: number[];
      n_filters: number[];
      pooling_type: 'max' | 'avg' | 'global';
    };
  };
  
  // Capabilities
  capabilities: {
    handles_variable_length: boolean;
    max_context_length: number;
    supports_attention_export: boolean;
    supports_uncertainty: boolean;
    uncertainty_method?: 'mcdropout' | 'ensemble' | 'conformal' | 'evidential';
  };
  
  // Performance characteristics
  performance: {
    inference_latency_ms: number;
    memory_mb: number;
    throughput_samples_per_sec: number;
    gpu_required: boolean;
  };
}

// =============================================================================
// ATTENTION VISUALIZATION
// =============================================================================

export interface AttentionPattern {
  pattern_id: string;
  prediction_id: string;
  model_id: string;
  
  // Input context
  input_sequence: {
    timestamps: string[];
    feature_names: string[];
    sequence_length: number;
  };
  
  // Attention weights by layer/head
  attention_weights: Array<{
    layer: number;
    head: number;
    weights: number[][];  // [query_pos, key_pos]
    
    // Aggregated patterns
    temporal_focus: {
      recent_weight: number;      // Attention to recent timesteps
      distant_weight: number;     // Attention to distant timesteps
      periodic_peaks?: number[];  // Detected periodic attention
    };
  }>;
  
  // Cross-feature attention (if applicable)
  cross_feature_attention?: {
    feature_pairs: Array<{
      source_feature: string;
      target_feature: string;
      attention_strength: number;
    }>;
  };
  
  // Interpretable summary
  summary: {
    most_attended_timesteps: Array<{
      timestep_idx: number;
      timestamp: string;
      aggregate_attention: number;
      reason?: string;
    }>;
    most_attended_features: Array<{
      feature_name: string;
      aggregate_attention: number;
    }>;
    attention_entropy: number;  // Higher = more diffuse attention
  };
}

export interface AttentionAnalysis {
  analysis_id: string;
  model_id: string;
  period: { start: string; end: string };
  n_predictions_analyzed: number;
  
  // Aggregate patterns
  aggregate_patterns: {
    avg_attention_entropy: number;
    temporal_focus_distribution: {
      recent_focused: number;    // % predictions focused on recent
      distant_focused: number;
      balanced: number;
    };
    
    // Feature importance from attention
    feature_importance_ranking: Array<{
      feature_name: string;
      avg_attention: number;
      attention_stability: number;  // How consistent across predictions
    }>;
  };
  
  // Anomalous attention patterns
  anomalies: Array<{
    prediction_id: string;
    anomaly_type: 'attention_collapse' | 'unexpected_focus' | 'periodic_mismatch';
    description: string;
    severity: 'low' | 'medium' | 'high';
  }>;
}

// =============================================================================
// ARCHITECTURE COMPARISON
// =============================================================================

export interface ArchitectureComparison {
  comparison_id: string;
  comparison_name: string;
  
  models: Array<{
    model_id: string;
    model_name: string;
    architecture: ModelArchitecture;
  }>;
  
  // Performance comparison
  performance_comparison: {
    metrics: Array<{
      metric_name: string;
      values: Record<string, number>;  // model_id -> value
      winner: string;
    }>;
    
    latency_comparison: Record<string, number>;
    memory_comparison: Record<string, number>;
  };
  
  // Task-specific suitability
  task_suitability: {
    task: 'anomaly_detection' | 'failure_prediction' | 'rul_estimation';
    
    rankings: Array<{
      model_id: string;
      rank: number;
      strengths: string[];
      weaknesses: string[];
    }>;
    
    recommendation: string;
  };
}

// =============================================================================
// LONG-RANGE DEPENDENCY ANALYSIS
// =============================================================================

export interface LongRangeDependencyAnalysis {
  analysis_id: string;
  model_id: string;
  
  // Capability assessment
  capability: {
    effective_context_length: number;  // How far back model actually uses
    theoretical_max_length: number;
    utilization_percent: number;
  };
  
  // Dependency decay
  dependency_decay: {
    bins: Array<{
      lag_hours: number;
      dependency_strength: number;  // 0-1, how much past info affects predictions
    }>;
    half_life_hours: number;  // When dependency drops to 50%
  };
  
  // Periodic pattern detection
  periodic_patterns: Array<{
    period_hours: number;
    strength: number;
    description: string;  // e.g., "Daily cycle", "Weekly pattern"
  }>;
  
  // Comparison to baseline
  vs_baseline: {
    baseline_model: string;
    improvement_in_long_range: number;
    contexts_where_matters: string[];
  };
}
