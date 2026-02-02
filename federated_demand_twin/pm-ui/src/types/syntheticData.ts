/**
 * Synthetic Data Governance Types
 * 
 * Defines types for GAN/diffusion-generated training data, augmentation tracking,
 * and synthetic failure trajectory validation.
 * Addresses research area D: Generative approaches for data imbalance.
 */

// =============================================================================
// GENERATIVE METHOD TYPES
// =============================================================================

export type GenerativeMethod = 
  | 'gan'                    // Generative Adversarial Network
  | 'conditional_gan'        // Class-conditional GAN
  | 'transformer_gan'        // Transformer-based GAN
  | 'diffusion'              // Denoising diffusion models
  | 'vae'                    // Variational Autoencoder
  | 'flow'                   // Normalizing flows
  | 'copula'                 // Statistical copula methods
  | 'smote_variants';        // SMOTE and variants for time series

export type SyntheticDataPurpose = 
  | 'class_balance'          // Balance failure vs normal
  | 'rare_event_augment'     // Augment rare failure modes
  | 'trajectory_extension'   // Extend degradation trajectories
  | 'domain_adaptation'      // Adapt to new asset types
  | 'privacy_preservation'   // Replace sensitive data
  | 'stress_testing';        // Generate edge cases

// =============================================================================
// GENERATIVE MODEL CONFIGURATION
// =============================================================================

export interface GenerativeModelConfig {
  config_id: string;
  model_name: string;
  description: string;
  
  // Method
  method: GenerativeMethod;
  method_params: {
    // GAN params
    generator_architecture?: string;
    discriminator_architecture?: string;
    latent_dim?: number;
    
    // Diffusion params
    n_diffusion_steps?: number;
    noise_schedule?: 'linear' | 'cosine' | 'sigmoid';
    
    // Conditioning
    conditioning: {
      conditioned: boolean;
      condition_on?: ('fault_type' | 'severity' | 'asset_type' | 'operating_mode')[];
    };
  };
  
  // Training data (real data used to train generator)
  training_data: {
    dataset_id: string;
    n_real_samples: number;
    fault_types_covered: string[];
    date_range: { start: string; end: string };
  };
  
  // Output characteristics
  output_config: {
    sequence_length: number;
    n_features: number;
    feature_names: string[];
    sampling_rate_hz: number;
  };
  
  // Status
  status: 'training' | 'validating' | 'approved' | 'rejected' | 'deprecated';
  created_at: string;
  approved_by?: string;
  approved_at?: string;
}

// =============================================================================
// SYNTHETIC DATA BATCH
// =============================================================================

export interface SyntheticDataBatch {
  batch_id: string;
  generator_id: string;
  generated_at: string;
  
  // Generation parameters
  generation_params: {
    purpose: SyntheticDataPurpose;
    n_samples: number;
    
    // Conditioning used
    conditions?: {
      fault_type?: string;
      severity?: string;
      asset_type?: string;
      rul_range?: { min_hours: number; max_hours: number };
    };
    
    // Diversity controls
    diversity_seed?: number;
    temperature?: number;
  };
  
  // Batch statistics
  statistics: {
    n_samples_generated: number;
    generation_time_sec: number;
    
    // Feature statistics
    feature_stats: Array<{
      feature_name: string;
      mean: number;
      std: number;
      min: number;
      max: number;
      vs_real_distribution: {
        kl_divergence: number;
        wasserstein_distance: number;
      };
    }>;
  };
  
  // Quality assessment
  quality: {
    fidelity_score: number;           // How realistic (0-1)
    diversity_score: number;          // How varied (0-1)
    utility_score: number;            // How useful for downstream (0-1)
    overall_quality: 'high' | 'medium' | 'low';
  };
  
  // Validation status
  validation: {
    validated: boolean;
    validation_method: 'automated' | 'human_review' | 'both';
    validator?: string;
    validation_notes?: string;
    approved_for_training: boolean;
  };
  
  // Storage
  storage_path: string;
  size_mb: number;
}

// =============================================================================
// SYNTHETIC DATA VALIDATION
// =============================================================================

export interface SyntheticDataValidation {
  validation_id: string;
  batch_id: string;
  validated_at: string;
  
  // Fidelity checks (does it look real?)
  fidelity_checks: {
    discriminator_score: number;      // If using GAN
    expert_plausibility: number;      // Human rating if available
    
    // Statistical tests
    statistical_tests: Array<{
      test_name: string;
      passed: boolean;
      p_value: number;
      details: string;
    }>;
    
    // Domain-specific checks
    domain_checks: Array<{
      check_name: string;
      passed: boolean;
      description: string;
    }>;
  };
  
  // Utility checks (does it help training?)
  utility_checks: {
    // Train with/without synthetic
    ablation_study?: {
      with_synthetic: {
        f1: number;
        recall: number;
        precision: number;
      };
      without_synthetic: {
        f1: number;
        recall: number;
        precision: number;
      };
      improvement_percent: number;
    };
    
    // Synthetic-to-real gap
    s2r_gap?: {
      performance_on_real_test: number;
      performance_on_synthetic_test: number;
      gap: number;
      acceptable: boolean;
    };
  };
  
  // Risk assessment
  risk_assessment: {
    overfitting_risk: 'low' | 'medium' | 'high';
    mode_collapse_detected: boolean;
    artifact_types_detected: string[];
    
    recommendations: string[];
  };
  
  // Final verdict
  verdict: {
    approved: boolean;
    approval_level: 'full' | 'conditional' | 'rejected';
    conditions?: string[];
    reviewer: string;
    review_notes: string;
  };
}

// =============================================================================
// DATA AUGMENTATION TRACKING
// =============================================================================

export interface AugmentationConfig {
  config_id: string;
  config_name: string;
  
  // Augmentation strategy
  strategy: {
    synthetic_ratio: number;          // e.g., 0.3 = 30% synthetic
    per_class_ratio: Record<string, number>;  // Class-specific ratios
    
    // Curriculum
    curriculum?: {
      start_ratio: number;
      end_ratio: number;
      warmup_epochs: number;
    };
  };
  
  // Source generators
  generators: Array<{
    generator_id: string;
    fault_types: string[];
    weight: number;
  }>;
  
  // Constraints
  constraints: {
    max_synthetic_per_batch: number;
    require_validation: boolean;
    min_quality_score: number;
  };
}

export interface AugmentedTrainingRun {
  run_id: string;
  augmentation_config_id: string;
  
  // Data composition
  data_composition: {
    total_samples: number;
    real_samples: number;
    synthetic_samples: number;
    synthetic_ratio_actual: number;
    
    by_class: Array<{
      class_name: string;
      real_count: number;
      synthetic_count: number;
      original_imbalance_ratio: number;
      final_imbalance_ratio: number;
    }>;
  };
  
  // Training outcome
  training_outcome: {
    epochs_completed: number;
    final_metrics: Record<string, number>;
    
    // Impact of synthetic data
    synthetic_impact: {
      real_only_baseline: Record<string, number>;
      with_synthetic: Record<string, number>;
      improvement: Record<string, number>;
    };
  };
  
  // Monitoring
  monitoring: {
    synthetic_samples_used: string[];  // Batch IDs
    validation_during_training: boolean;
    issues_detected: string[];
  };
}

// =============================================================================
// SYNTHETIC DATA LINEAGE
// =============================================================================

export interface SyntheticDataLineage {
  lineage_id: string;
  
  // Trace from model prediction back to synthetic data
  prediction: {
    prediction_id: string;
    model_id: string;
    model_version: string;
  };
  
  // Training data composition
  training_data: {
    total_samples: number;
    synthetic_samples: number;
    synthetic_ratio: number;
    
    synthetic_batches: Array<{
      batch_id: string;
      n_samples_used: number;
      generator_id: string;
      generation_date: string;
    }>;
  };
  
  // Generator lineage
  generators: Array<{
    generator_id: string;
    method: GenerativeMethod;
    training_data_source: string;
    validation_status: string;
  }>;
  
  // Audit trail
  audit: {
    synthetic_data_approved_by: string;
    approved_at: string;
    governance_notes: string;
  };
}

// =============================================================================
// SYNTHETIC DATA GOVERNANCE DASHBOARD
// =============================================================================

export interface SyntheticDataDashboard {
  dashboard_id: string;
  generated_at: string;
  
  // Generator inventory
  generators: {
    total: number;
    by_status: Record<string, number>;
    by_method: Record<GenerativeMethod, number>;
  };
  
  // Batch summary
  batches: {
    total_generated: number;
    total_approved: number;
    total_samples: number;
    avg_quality_score: number;
    
    recent_batches: Array<{
      batch_id: string;
      generated_at: string;
      n_samples: number;
      quality: string;
      status: string;
    }>;
  };
  
  // Usage in training
  training_usage: {
    models_using_synthetic: number;
    avg_synthetic_ratio: number;
    avg_improvement_from_synthetic: number;
  };
  
  // Quality trends
  quality_trends: Array<{
    period: string;
    avg_fidelity: number;
    avg_utility: number;
    rejection_rate: number;
  }>;
  
  // Alerts
  alerts: Array<{
    severity: 'info' | 'warning' | 'error';
    message: string;
    affected_items: string[];
  }>;
}
