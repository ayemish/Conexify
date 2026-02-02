import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Alert,
  Tooltip,
  IconButton,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  People as PeopleIcon,
  AccountTree as CrewIcon,
  TrendingUp as RevenueIcon,
  TrendingDown as CostIcon,
  Balance as BalanceIcon,
  Savings as MarginIcon,
  Refresh as RefreshIcon,
  Lightbulb as DecisionIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  ArrowForward as ArrowIcon,
  Science as ScienceIcon,
  Shield as ShieldIcon,
  Category as CategoryIcon,
  Speed as SpeedIcon,
  Verified as VerifiedIcon,
} from '@mui/icons-material';

interface Agent {
  agent_id: string;
  role: string;
  goal: string;
  backstory: string;
  tools: string[];
  allow_delegation: boolean;
  verbose: boolean;
  status?: string;
}

interface LevelCrew {
  crew_id: string;
  name: string;
  description: string;
  agents: string[];
}

interface ScenarioCrew {
  crew_id: string;
  name: string;
  description: string;
  objective: string;
  kpis: string[];
}

interface CrewInstance {
  instance_id: string;
  crew_type: string;
  entity_id?: string;
  entity_name?: string;
  rmn_id?: string;
  rmn_name?: string;
  channel_id?: string;
  channel_name?: string;
  status: string;
  last_run?: string;
  efficiency?: number;
  total_spend?: number;
  spend?: number;
  channels?: string[];
  budget?: number;
  projected_impact?: number;
  created_at?: string;
}

interface BusinessScenario {
  scenario_id: string;
  name: string;
  description: string;
  category: string;
  objective_type: string;
  objective_description: string;
  default_risk_appetite: string;
  default_cadence: string;
  icon: string;
  color: string;
  tags: string[];
  required_crews: string[];
}

interface RecommendedAction {
  action_id: string;
  action_type: string;
  entity_type: string;
  entity_name: string;
  description: string;
  current_value: number;
  recommended_value: number;
  delta: number;
  delta_pct: number;
  expected_impact: number;
  confidence: number;
  priority: number;
  rationale: string;
}

interface EvidenceItem {
  evidence_id: string;
  evidence_type: string;
  title: string;
  description: string;
  metric_name: string;
  metric_value: number;
  confidence_interval?: number[];
  probability?: number;
}

interface ReasoningStep {
  step_id: string;
  step_number: number;
  crew_id: string;
  agent_id: string;
  action: string;
  input_summary: string;
  output_summary: string;
  reasoning: string;
  confidence: number;
}

interface DecisionRecommendation {
  recommendation_id: string;
  scenario_id: string;
  scenario_name: string;
  executive_summary: string;
  recommended_actions: RecommendedAction[];
  supporting_evidence: EvidenceItem[];
  reasoning_chain: {
    chain_id: string;
    steps: ReasoningStep[];
    crews_involved: string[];
    cross_crew_messages: any[];
  };
  total_expected_impact: number;
  overall_confidence: number;
  risk_assessment: string;
  constraints_satisfied: boolean;
  constraint_violations: string[];
}

interface CrewsData {
  level_crews: LevelCrew[];
  scenario_crews: ScenarioCrew[];
}

interface InstancesData {
  brand_crews: CrewInstance[];
  rmn_crews: CrewInstance[];
  channel_crews: CrewInstance[];
  scenario_crews: CrewInstance[];
}

interface ScenariosData {
  scenarios: BusinessScenario[];
}

interface DecisionResult {
  success: boolean;
  decision_recommendation: DecisionRecommendation | null;
  execution_time_ms: number;
  crews_executed: string[];
}

const agentDefinitions: Record<string, Agent> = {
  brand_portfolio_lead: {
    agent_id: 'brand_portfolio_lead',
    role: 'Brand Portfolio Lead',
    goal: 'Own decision logic, align to outcome, and resolve tradeoffs across brand portfolio',
    backstory: 'Senior brand marketing strategist with 15+ years experience in CPG retail media. Makes final allocation decisions by balancing growth, efficiency, and brand priorities.',
    tools: ['decision_framework_tool', 'tradeoff_analyzer_tool'],
    allow_delegation: true,
    verbose: true,
  },
  brand_performance_analyst: {
    agent_id: 'brand_performance_analyst',
    role: 'Brand Performance Analyst',
    goal: 'Compute KPIs, identify winners/losers, and quantify contribution to totals',
    backstory: 'Expert at analyzing brand performance data. Computes key metrics like spend efficiency, incremental sales, and ROAS.',
    tools: ['kpi_calculator_tool', 'trend_analyzer_tool', 'benchmark_tool'],
    allow_delegation: false,
    verbose: false,
  },
  incrementality_analyst: {
    agent_id: 'incrementality_analyst',
    role: 'Incrementality Analyst',
    goal: 'Validate lift methodology and interpret marginal returns/response curves',
    backstory: 'Measurement scientist specializing in incrementality testing and media mix modeling.',
    tools: ['lift_validation_tool', 'response_curve_tool', 'saturation_detector_tool'],
    allow_delegation: false,
    verbose: false,
  },
  margin_mix_analyst: {
    agent_id: 'margin_mix_analyst',
    role: 'Margin & Mix Analyst',
    goal: 'Incorporate gross margin, SKU mix, and price/promo interactions',
    backstory: 'Analyzes profitability at the product level. Optimizes for profitable growth, not just revenue.',
    tools: ['margin_calculator_tool', 'sku_mix_analyzer_tool', 'promo_impact_tool'],
    allow_delegation: false,
    verbose: false,
  },
  budget_allocation_optimizer: {
    agent_id: 'budget_allocation_optimizer',
    role: 'Budget Allocation Optimizer',
    goal: 'Solve allocation under constraints using marginal ROAS equalization',
    backstory: 'Optimization expert who finds the best allocation of budget across channels and RMNs using mathematical optimization.',
    tools: ['optimizer_tool', 'constraint_solver_tool', 'sensitivity_analyzer_tool'],
    allow_delegation: false,
    verbose: false,
  },
  constraints_risk_manager: {
    agent_id: 'constraints_risk_manager',
    role: 'Constraints & Risk Manager',
    goal: 'Enforce floors/ceilings, retailer obligations, and brand safety constraints',
    backstory: 'Ensures all recommendations comply with business constraints including minimum spend requirements and brand safety policies.',
    tools: ['constraint_validator_tool', 'risk_scorer_tool', 'compliance_checker_tool'],
    allow_delegation: false,
    verbose: false,
  },
  recommendation_narrator: {
    agent_id: 'recommendation_narrator',
    role: 'Recommendation Narrator',
    goal: 'Produce stakeholder-ready narrative and action list',
    backstory: 'Translates complex optimization outputs into clear, actionable recommendations with executive summaries.',
    tools: ['narrative_generator_tool', 'action_list_formatter_tool'],
    allow_delegation: false,
    verbose: false,
  },
  qa_auditor: {
    agent_id: 'qa_auditor',
    role: 'QA Auditor',
    goal: 'Verify math consistency, unit sanity, and completeness',
    backstory: 'Meticulous about data quality and consistency. Catches errors before they reach stakeholders.',
    tools: ['math_validator_tool', 'reconciliation_tool', 'completeness_checker_tool'],
    allow_delegation: false,
    verbose: false,
  },
  rmn_account_lead: {
    agent_id: 'rmn_account_lead',
    role: 'RMN Account Lead',
    goal: 'Align recommendations with retailer realities and commercial terms',
    backstory: 'Dedicated account lead who understands retailer-specific media capabilities, audience segments, and commercial terms.',
    tools: ['retailer_playbook_tool', 'commitment_tracker_tool'],
    allow_delegation: true,
    verbose: true,
  },
  rmn_performance_analyst: {
    agent_id: 'rmn_performance_analyst',
    role: 'RMN Performance Analyst',
    goal: 'Compute network-level trends and decompose by brand/channel',
    backstory: 'Expert at analyzing retail media network performance including spend efficiency and share of voice.',
    tools: ['rmn_kpi_tool', 'trend_analyzer_tool', 'decomposition_tool'],
    allow_delegation: false,
    verbose: false,
  },
  auction_dynamics_specialist: {
    agent_id: 'auction_dynamics_specialist',
    role: 'Auction Dynamics Specialist',
    goal: 'Interpret CPC/CPM dynamics, competition, and share-of-voice signals',
    backstory: 'Understands auction mechanics of retail media platforms and identifies opportunities to win more efficiently.',
    tools: ['auction_analyzer_tool', 'bid_landscape_tool', 'sov_tracker_tool'],
    allow_delegation: false,
    verbose: false,
  },
  campaign_ops_lead: {
    agent_id: 'campaign_ops_lead',
    role: 'Campaign Ops Lead',
    goal: 'Ensure changes are implementable and aligned to outcome and pacing',
    backstory: 'Leads campaign operations ensuring all recommendations can be executed within platform constraints.',
    tools: ['campaign_manager_tool', 'pacing_tracker_tool'],
    allow_delegation: true,
    verbose: true,
  },
  campaign_performance_analyst: {
    agent_id: 'campaign_performance_analyst',
    role: 'Campaign Performance Analyst',
    goal: 'Compute campaign and message KPIs and rank opportunities',
    backstory: 'Analyzes campaign performance at granular levels and surfaces actionable insights.',
    tools: ['campaign_kpi_tool', 'performance_ranker_tool', 'saturation_detector_tool'],
    allow_delegation: false,
    verbose: false,
  },
  audience_keyword_analyst: {
    agent_id: 'audience_keyword_analyst',
    role: 'Audience/Keyword Analyst',
    goal: 'Diagnose targeting quality and demand capture vs demand creation',
    backstory: 'Expert in audience segmentation and keyword strategy. Identifies expansion opportunities.',
    tools: ['audience_analyzer_tool', 'keyword_tool', 'intent_classifier_tool'],
    allow_delegation: false,
    verbose: false,
  },
  creative_message_analyst: {
    agent_id: 'creative_message_analyst',
    role: 'Creative/Message Analyst',
    goal: 'Evaluate message themes and formats; flag fatigue and misalignment',
    backstory: 'Analyzes creative performance and message effectiveness. Recommends refresh cycles.',
    tools: ['creative_analyzer_tool', 'fatigue_detector_tool', 'message_scorer_tool'],
    allow_delegation: false,
    verbose: false,
  },
  experimentation_designer: {
    agent_id: 'experimentation_designer',
    role: 'Experimentation Designer',
    goal: 'Define A/B and multivariate tests with required sample sizes',
    backstory: 'Designs statistically rigorous experiments to improve campaign performance.',
    tools: ['experiment_designer_tool', 'sample_size_calculator_tool'],
    allow_delegation: false,
    verbose: false,
  },
  bidding_pacing_specialist: {
    agent_id: 'bidding_pacing_specialist',
    role: 'Bidding/Pacing Specialist',
    goal: 'Define bid/budget rules and pacing guardrails',
    backstory: 'Optimizes bidding strategies and budget pacing to maximize efficiency.',
    tools: ['bid_optimizer_tool', 'pacing_tool', 'daypart_analyzer_tool'],
    allow_delegation: false,
    verbose: false,
  },
  channel_strategy_lead: {
    agent_id: 'channel_strategy_lead',
    role: 'Channel Strategy Lead',
    goal: 'Align cross-channel tradeoffs to outcome and time window',
    backstory: 'Leads cross-channel media strategy, balancing investment across Search, Display, Video, and Email.',
    tools: ['channel_planner_tool', 'tradeoff_analyzer_tool'],
    allow_delegation: true,
    verbose: true,
  },
  search_specialist: {
    agent_id: 'search_specialist',
    role: 'Search Specialist',
    goal: 'Optimize search channel performance through keywords and bids',
    backstory: 'Expert in retail media search advertising. Optimizes keyword portfolios and bid strategies.',
    tools: ['keyword_tool', 'bid_optimizer_tool', 'search_term_analyzer_tool'],
    allow_delegation: false,
    verbose: false,
  },
  display_specialist: {
    agent_id: 'display_specialist',
    role: 'Display Specialist',
    goal: 'Optimize display channel through audiences and placements',
    backstory: 'Specializes in display advertising on retail media networks. Optimizes audience targeting.',
    tools: ['audience_tool', 'placement_analyzer_tool', 'frequency_tool'],
    allow_delegation: false,
    verbose: false,
  },
  video_specialist: {
    agent_id: 'video_specialist',
    role: 'Video Specialist',
    goal: 'Optimize video channel through creative and targeting',
    backstory: 'Expert in video advertising including CTV and online video.',
    tools: ['video_analyzer_tool', 'ctv_planner_tool', 'creative_tool'],
    allow_delegation: false,
    verbose: false,
  },
  email_specialist: {
    agent_id: 'email_specialist',
    role: 'Email Specialist',
    goal: 'Optimize email channel through segmentation and messaging',
    backstory: 'Specializes in email marketing within retail media.',
    tools: ['email_segmentation_tool', 'send_time_optimizer_tool', 'content_analyzer_tool'],
    allow_delegation: false,
    verbose: false,
  },
  scenario_director: {
    agent_id: 'scenario_director',
    role: 'Scenario Director',
    goal: 'Final decision-maker; select which sub-crews to invoke',
    backstory: 'Chief strategist who orchestrates complex optimization scenarios.',
    tools: ['crew_invoker_tool', 'decision_framework_tool'],
    allow_delegation: true,
    verbose: true,
  },
  scenario_intake_analyst: {
    agent_id: 'scenario_intake_analyst',
    role: 'Scenario Intake Analyst',
    goal: 'Normalize scenario inputs and resolve missing parameters',
    backstory: 'Processes scenario requests and ensures all required parameters are valid.',
    tools: ['parameter_validator_tool', 'default_resolver_tool'],
    allow_delegation: false,
    verbose: false,
  },
  objective_router: {
    agent_id: 'objective_router',
    role: 'Objective Router',
    goal: 'Set objective weights and KPI floors based on desired outcome',
    backstory: 'Translates business objectives into mathematical optimization parameters.',
    tools: ['objective_configurator_tool'],
    allow_delegation: false,
    verbose: false,
  },
  response_curve_modeler: {
    agent_id: 'response_curve_modeler',
    role: 'Response Curve Modeler',
    goal: 'Estimate marginal return curves and uncertainty bands',
    backstory: 'Estimates response curves from historical data with uncertainty quantification.',
    tools: ['curve_fitter_tool', 'uncertainty_estimator_tool'],
    allow_delegation: false,
    verbose: false,
  },
  optimization_solver: {
    agent_id: 'optimization_solver',
    role: 'Optimization Solver',
    goal: 'Produce optimal allocation and optional discrete actions',
    backstory: 'Mathematical optimizer that solves for the allocation that maximizes objectives.',
    tools: ['solver_tool', 'shadow_price_calculator_tool'],
    allow_delegation: false,
    verbose: false,
  },
  sensitivity_robustness_analyst: {
    agent_id: 'sensitivity_robustness_analyst',
    role: 'Sensitivity & Robustness Analyst',
    goal: 'Stress-test plans and identify fragile recommendations',
    backstory: 'Tests robustness of optimization solutions through sensitivity analysis.',
    tools: ['sensitivity_tool', 'stress_test_tool', 'monte_carlo_tool'],
    allow_delegation: false,
    verbose: false,
  },
  scenario_comparator: {
    agent_id: 'scenario_comparator',
    role: 'Scenario Comparator',
    goal: 'Generate multi-scenario tables and narratives',
    backstory: 'Compares multiple scenarios and creates clear comparisons for decision-makers.',
    tools: ['comparison_generator_tool', 'tradeoff_visualizer_tool'],
    allow_delegation: false,
    verbose: false,
  },
};

const OptimizationCrewsPage: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [crewsData, setCrewsData] = useState<CrewsData | null>(null);
  const [instancesData, setInstancesData] = useState<InstancesData | null>(null);
  const [scenariosData, setScenariosData] = useState<ScenariosData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCrew, setExpandedCrew] = useState<string | false>(false);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [decisionResult, setDecisionResult] = useState<DecisionResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [riskAppetite, setRiskAppetite] = useState<string>('balanced');
  const [maxReallocation, setMaxReallocation] = useState<number>(15);
  const [explorationBudget, setExplorationBudget] = useState<number>(10);
  const [agentRecommendations, setAgentRecommendations] = useState<any>(null);
  const [loadingRecommendations, setLoadingRecommendations] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [crewsRes, instancesRes, scenariosRes] = await Promise.all([
        fetch('/api/crews/list'),
        fetch('/api/crews/instances'),
        fetch('/api/scenarios/list'),
      ]);
      
      if (crewsRes.ok && instancesRes.ok) {
        setCrewsData(await crewsRes.json());
        setInstancesData(await instancesRes.json());
      } else {
        setError('Failed to load crews data');
      }
      
      if (scenariosRes.ok) {
        setScenariosData(await scenariosRes.json());
      }
    } catch (err) {
      setError('Error connecting to API');
    } finally {
      setLoading(false);
    }
  };

  const executeScenario = async (scenarioId: string) => {
    setExecuting(true);
    setDecisionResult(null);
    try {
      const response = await fetch('/api/scenarios/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scenarioId,
          risk_appetite: riskAppetite,
          max_reallocation_pct: maxReallocation / 100,
          exploration_budget_pct: explorationBudget / 100,
        }),
      });
      if (response.ok) {
        const result = await response.json();
        setDecisionResult(result);
      }
    } catch (err) {
      console.error('Scenario execution error:', err);
    } finally {
      setExecuting(false);
    }
  };

  const fetchAgentRecommendations = async () => {
    setLoadingRecommendations(true);
    try {
      const response = await fetch('/api/scenarios/execute-with-crews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: 'grow_revenue_brand',
          selection_mode: 'agent_recommended',
          risk_appetite: riskAppetite,
          max_reallocation_pct: maxReallocation / 100,
          exploration_budget_pct: explorationBudget / 100,
          current_state: {
            revenue_trend: 0.08,
            efficiency_trend: 0.02,
            competitive_pressure: 0.5,
          },
        }),
      });
      if (response.ok) {
        const result = await response.json();
        setAgentRecommendations(result);
      }
    } catch (err) {
      console.error('Failed to fetch agent recommendations:', err);
    } finally {
      setLoadingRecommendations(false);
    }
  };

  useEffect(() => {
    if (tabValue === 4 && !agentRecommendations) {
      fetchAgentRecommendations();
    }
  }, [tabValue]);

  const getScenarioCategoryColor = (category: string): string => {
    switch (category) {
      case 'core_outcome': return '#4CAF50';
      case 'incrementality': return '#2196F3';
      case 'risk_governance': return '#9C27B0';
      case 'portfolio': return '#FF9800';
      case 'operational': return '#607D8B';
      default: return '#757575';
    }
  };

  const getScenarioIconComponent = (icon: string) => {
    switch (icon) {
      case 'trending_up': return <RevenueIcon />;
      case 'balance': return <BalanceIcon />;
      case 'shield': return <ShieldIcon />;
      case 'attach_money': return <MarginIcon />;
      case 'savings': return <MarginIcon />;
      case 'verified': return <VerifiedIcon />;
      case 'person_add': return <PeopleIcon />;
      case 'security': return <ShieldIcon />;
      case 'category': return <CategoryIcon />;
      case 'science': return <ScienceIcon />;
      case 'speed': return <SpeedIcon />;
      default: return <DecisionIcon />;
    }
  };

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
      case 'completed':
        return 'success';
      case 'running':
        return 'primary';
      case 'idle':
      case 'queued':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getScenarioIcon = (crewId: string) => {
    switch (crewId) {
      case 'increase_revenue':
        return <RevenueIcon color="success" />;
      case 'increase_margin':
        return <MarginIcon color="primary" />;
      case 'maintain_revenue':
        return <BalanceIcon color="info" />;
      case 'reduce_cost':
        return <CostIcon color="warning" />;
      default:
        return <CrewIcon />;
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={3}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box p={3}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h4" gutterBottom>
            Optimization Crews
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Multi-level CrewAI agent teams for retail media spend optimization
          </Typography>
        </Box>
        <IconButton onClick={fetchData} color="primary">
          <RefreshIcon />
        </IconButton>
      </Box>

      <Tabs value={tabValue} onChange={handleTabChange} sx={{ mb: 3 }}>
        <Tab label="Crew Definitions" icon={<CrewIcon />} iconPosition="start" />
        <Tab label="Active Instances" icon={<PeopleIcon />} iconPosition="start" />
        <Tab label="All Agents" icon={<PeopleIcon />} iconPosition="start" />
        <Tab label="Decision Support" icon={<DecisionIcon />} iconPosition="start" />
        <Tab label="Recommendations" icon={<RevenueIcon />} iconPosition="start" />
      </Tabs>

      {tabValue === 0 && crewsData && (
        <Box>
          <Typography variant="h6" gutterBottom>Level Crews</Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Optimization by analytical level: Brand, RMN, Campaign/Message, Channel
          </Typography>
          
          <Grid container spacing={2} mb={4}>
            {crewsData.level_crews.map((crew) => (
              <Grid item xs={12} md={6} key={crew.crew_id}>
                <Accordion
                  expanded={expandedCrew === crew.crew_id}
                  onChange={() => setExpandedCrew(expandedCrew === crew.crew_id ? false : crew.crew_id)}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box display="flex" alignItems="center" gap={2} width="100%">
                      <CrewIcon color="primary" />
                      <Box flex={1}>
                        <Typography variant="subtitle1" fontWeight="bold">
                          {crew.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {crew.agents.length} agents
                        </Typography>
                      </Box>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" mb={2}>{crew.description}</Typography>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="subtitle2" mb={1}>Agents:</Typography>
                    <Box display="flex" flexWrap="wrap" gap={1}>
                      {crew.agents.map((agentId) => {
                        const agent = agentDefinitions[agentId];
                        return (
                          <Tooltip
                            key={agentId}
                            title={agent ? `${agent.goal}` : agentId}
                            arrow
                          >
                            <Chip
                              label={agent?.role || agentId}
                              size="small"
                              variant={agent?.allow_delegation ? 'filled' : 'outlined'}
                              color={agent?.allow_delegation ? 'primary' : 'default'}
                            />
                          </Tooltip>
                        );
                      })}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Grid>
            ))}
          </Grid>

          <Typography variant="h6" gutterBottom>Scenario Crews</Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Objective-based optimization: Increase Revenue, Increase Margin, Maintain Revenue, Reduce Cost
          </Typography>
          
          <Grid container spacing={2}>
            {crewsData.scenario_crews.map((crew) => (
              <Grid item xs={12} sm={6} md={3} key={crew.crew_id}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Box display="flex" alignItems="center" gap={1} mb={1}>
                      {getScenarioIcon(crew.crew_id)}
                      <Typography variant="subtitle1" fontWeight="bold">
                        {crew.name}
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" mb={2}>
                      {crew.description}
                    </Typography>
                    <Typography variant="caption" color="primary" display="block" mb={1}>
                      Objective: {crew.objective}
                    </Typography>
                    <Box display="flex" flexWrap="wrap" gap={0.5}>
                      {crew.kpis.slice(0, 3).map((kpi) => (
                        <Chip key={kpi} label={kpi} size="small" variant="outlined" />
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {tabValue === 1 && instancesData && (
        <Box>
          <Typography variant="h6" gutterBottom>Brand Crews</Typography>
          <TableContainer component={Paper} sx={{ mb: 4 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Brand</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Efficiency (iROAS)</TableCell>
                  <TableCell align="right">Total Spend</TableCell>
                  <TableCell>Last Run</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {instancesData.brand_crews.map((instance) => (
                  <TableRow key={instance.instance_id}>
                    <TableCell>{instance.entity_name}</TableCell>
                    <TableCell>
                      <Chip
                        label={instance.status}
                        size="small"
                        color={getStatusColor(instance.status) as any}
                      />
                    </TableCell>
                    <TableCell align="right">
                      {instance.efficiency?.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {instance.total_spend ? formatCurrency(instance.total_spend) : '-'}
                    </TableCell>
                    <TableCell>
                      {instance.last_run ? new Date(instance.last_run).toLocaleDateString() : '-'}
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" color="primary">
                        <PlayIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="h6" gutterBottom>RMN Crews</Typography>
          <TableContainer component={Paper} sx={{ mb: 4 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Retail Media Network</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Channels</TableCell>
                  <TableCell align="right">Efficiency</TableCell>
                  <TableCell align="right">Total Spend</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {instancesData.rmn_crews.map((instance) => (
                  <TableRow key={instance.instance_id}>
                    <TableCell fontWeight="bold">{instance.entity_name}</TableCell>
                    <TableCell>
                      <Chip
                        label={instance.status}
                        size="small"
                        color={getStatusColor(instance.status) as any}
                      />
                    </TableCell>
                    <TableCell>
                      {instance.channels?.join(', ')}
                    </TableCell>
                    <TableCell align="right">
                      {instance.efficiency?.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {instance.total_spend ? formatCurrency(instance.total_spend) : '-'}
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" color="primary">
                        <PlayIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="h6" gutterBottom>Scenario Crews</Typography>
          <Grid container spacing={2}>
            {instancesData.scenario_crews.map((instance) => (
              <Grid item xs={12} sm={6} md={3} key={instance.instance_id}>
                <Card>
                  <CardContent>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      {getScenarioIcon(instance.crew_type)}
                      <Chip
                        label={instance.status}
                        size="small"
                        color={getStatusColor(instance.status) as any}
                      />
                    </Box>
                    <Typography variant="subtitle2">
                      {instance.crew_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </Typography>
                    {instance.budget && (
                      <Typography variant="body2" color="text.secondary">
                        Budget: {formatCurrency(instance.budget)}
                      </Typography>
                    )}
                    {instance.projected_impact && (
                      <Box mt={1}>
                        <Typography variant="caption" color="text.secondary">
                          Projected Impact: +{(instance.projected_impact * 100).toFixed(1)}%
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={instance.projected_impact * 100 * 5}
                          color="success"
                          sx={{ mt: 0.5 }}
                        />
                      </Box>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {tabValue === 2 && (
        <Box>
          <Typography variant="h6" gutterBottom>
            All CrewAI Agents ({Object.keys(agentDefinitions).length})
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={3}>
            Complete catalog of CrewAI-compliant agents for retail media optimization
          </Typography>
          
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Role</TableCell>
                  <TableCell>Goal</TableCell>
                  <TableCell>Tools</TableCell>
                  <TableCell>Delegation</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.values(agentDefinitions).map((agent) => (
                  <TableRow key={agent.agent_id}>
                    <TableCell>
                      <Box>
                        <Typography variant="subtitle2">{agent.role}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {agent.agent_id}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={agent.backstory} arrow>
                        <Typography variant="body2" sx={{ maxWidth: 300 }}>
                          {agent.goal}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Box display="flex" flexWrap="wrap" gap={0.5}>
                        {agent.tools.map((tool) => (
                          <Chip
                            key={tool}
                            label={tool.replace(/_tool$/, '').replace(/_/g, ' ')}
                            size="small"
                            variant="outlined"
                          />
                        ))}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {agent.allow_delegation ? (
                        <Chip label="Yes" size="small" color="primary" />
                      ) : (
                        <Chip label="No" size="small" variant="outlined" />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {tabValue === 3 && (
        <Box>
          {/* Decision Support Header - Outcomes Focus */}
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 2, 
            mb: 3,
            p: 3,
            bgcolor: 'linear-gradient(135deg, #2E7D32 0%, #1B5E20 100%)',
            background: 'linear-gradient(135deg, #2E7D32 0%, #1B5E20 100%)',
            borderRadius: 2,
            color: 'white'
          }}>
            <Box sx={{ 
              width: 56, 
              height: 56, 
              borderRadius: 2, 
              bgcolor: 'rgba(255,255,255,0.2)', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <DecisionIcon sx={{ fontSize: 28 }} />
            </Box>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="h5" fontWeight="bold">Decision Support</Typography>
                <Chip 
                  label="OUTCOMES VIEW" 
                  size="small" 
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 'bold',
                    fontSize: '0.65rem',
                    letterSpacing: '0.05em'
                  }} 
                />
              </Box>
              <Typography variant="body2" sx={{ opacity: 0.9, mt: 0.5 }}>
                What actions to take and why — actionable recommendations with quantified impact
              </Typography>
            </Box>
            <Box sx={{ textAlign: 'right' }}>
              <Chip 
                icon={<VerifiedIcon sx={{ color: 'white !important' }} />}
                label="Evidence-Based" 
                sx={{ 
                  bgcolor: 'rgba(255,255,255,0.15)', 
                  color: 'white',
                  '& .MuiChip-icon': { color: 'white' }
                }} 
              />
            </Box>
          </Box>

          {/* Scenario Controls */}
          <Card sx={{ mb: 3, p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Optimization Parameters
            </Typography>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Risk Appetite</Typography>
                  <Box display="flex" gap={1} mt={0.5}>
                    {['conservative', 'balanced', 'aggressive'].map((level) => (
                      <Chip
                        key={level}
                        label={level.charAt(0).toUpperCase() + level.slice(1)}
                        size="small"
                        color={riskAppetite === level ? 'primary' : 'default'}
                        onClick={() => setRiskAppetite(level)}
                        variant={riskAppetite === level ? 'filled' : 'outlined'}
                      />
                    ))}
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Max Reallocation: {maxReallocation}%
                  </Typography>
                  <Box display="flex" gap={1} mt={0.5}>
                    {[5, 10, 15, 20, 30].map((pct) => (
                      <Chip
                        key={pct}
                        label={`${pct}%`}
                        size="small"
                        color={maxReallocation === pct ? 'primary' : 'default'}
                        onClick={() => setMaxReallocation(pct)}
                        variant={maxReallocation === pct ? 'filled' : 'outlined'}
                      />
                    ))}
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Exploration Budget: {explorationBudget}%
                  </Typography>
                  <Box display="flex" gap={1} mt={0.5}>
                    {[5, 10, 15, 20].map((pct) => (
                      <Chip
                        key={pct}
                        label={`${pct}%`}
                        size="small"
                        color={explorationBudget === pct ? 'primary' : 'default'}
                        onClick={() => setExplorationBudget(pct)}
                        variant={explorationBudget === pct ? 'filled' : 'outlined'}
                      />
                    ))}
                  </Box>
                </Box>
              </Grid>
            </Grid>
          </Card>

          {/* Scenario Categories */}
          {scenariosData?.scenarios && (
            <Box>
              {['core_outcome', 'incrementality', 'risk_governance', 'portfolio', 'operational'].map((category) => {
                const categoryScenarios = scenariosData.scenarios.filter(s => s.category === category);
                if (categoryScenarios.length === 0) return null;
                const categoryTitle = category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                return (
                  <Box key={category} mb={3}>
                    <Typography variant="subtitle1" fontWeight="bold" mb={1} sx={{ color: getScenarioCategoryColor(category) }}>
                      {categoryTitle}
                    </Typography>
                    <Grid container spacing={2}>
                      {categoryScenarios.map((scenario) => (
                        <Grid item xs={12} sm={6} md={4} key={scenario.scenario_id}>
                          <Card
                            sx={{
                              cursor: 'pointer',
                              border: selectedScenario === scenario.scenario_id ? '2px solid' : '1px solid',
                              borderColor: selectedScenario === scenario.scenario_id ? scenario.color : 'divider',
                              '&:hover': { boxShadow: 3 },
                            }}
                            onClick={() => setSelectedScenario(scenario.scenario_id)}
                          >
                            <CardContent>
                              <Box display="flex" alignItems="center" gap={1} mb={1}>
                                <Box sx={{ color: scenario.color }}>
                                  {getScenarioIconComponent(scenario.icon)}
                                </Box>
                                <Typography variant="subtitle2" fontWeight="bold">
                                  {scenario.name}
                                </Typography>
                              </Box>
                              <Typography variant="body2" color="text.secondary" mb={1}>
                                {scenario.description}
                              </Typography>
                              <Box display="flex" flexWrap="wrap" gap={0.5} mb={1}>
                                {scenario.tags.slice(0, 3).map((tag) => (
                                  <Chip key={tag} label={tag} size="small" variant="outlined" />
                                ))}
                              </Box>
                              <Box display="flex" justifyContent="space-between" alignItems="center">
                                <Typography variant="caption" color="text.secondary">
                                  {scenario.required_crews.length} crews
                                </Typography>
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={(e: React.MouseEvent) => {
                                    e.stopPropagation();
                                    setSelectedScenario(scenario.scenario_id);
                                    executeScenario(scenario.scenario_id);
                                  }}
                                  disabled={executing}
                                >
                                  <PlayIcon />
                                </IconButton>
                              </Box>
                            </CardContent>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  </Box>
                );
              })}
            </Box>
          )}

          {/* Execution Progress */}
          {executing && (
            <Card sx={{ mb: 3, p: 2 }}>
              <Box display="flex" alignItems="center" gap={2}>
                <CircularProgress size={24} />
                <Typography>Executing scenario across crews...</Typography>
              </Box>
              <LinearProgress sx={{ mt: 2 }} />
            </Card>
          )}

          {/* Decision Recommendation Results */}
          {decisionResult?.decision_recommendation && (
            <Box>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" gutterBottom display="flex" alignItems="center" gap={1}>
                <CheckIcon color="success" />
                Decision Recommendation
              </Typography>

              {/* Executive Summary */}
              <Alert severity="info" sx={{ mb: 3 }}>
                <Typography variant="body2">
                  {decisionResult.decision_recommendation.executive_summary}
                </Typography>
              </Alert>

              {/* Key Metrics */}
              <Grid container spacing={2} mb={3}>
                <Grid item xs={6} sm={3}>
                  <Card sx={{ textAlign: 'center', p: 2 }}>
                    <Typography variant="h5" color="success.main">
                      {formatCurrency(decisionResult.decision_recommendation.total_expected_impact)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Expected Impact
                    </Typography>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card sx={{ textAlign: 'center', p: 2 }}>
                    <Typography variant="h5" color="primary.main">
                      {(decisionResult.decision_recommendation.overall_confidence * 100).toFixed(0)}%
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Confidence
                    </Typography>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card sx={{ textAlign: 'center', p: 2 }}>
                    <Typography variant="h5">
                      {decisionResult.decision_recommendation.recommended_actions.length}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Actions
                    </Typography>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card sx={{ textAlign: 'center', p: 2 }}>
                    <Chip
                      label={decisionResult.decision_recommendation.constraints_satisfied ? 'Satisfied' : 'Violations'}
                      color={decisionResult.decision_recommendation.constraints_satisfied ? 'success' : 'warning'}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                      Constraints
                    </Typography>
                  </Card>
                </Grid>
              </Grid>

              {/* Recommended Actions Table */}
              <Typography variant="subtitle1" fontWeight="bold" mb={1}>
                Recommended Actions
              </Typography>
              <TableContainer component={Paper} sx={{ mb: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Priority</TableCell>
                      <TableCell>Entity</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell align="right">Current</TableCell>
                      <TableCell align="right">Recommended</TableCell>
                      <TableCell align="right">Delta</TableCell>
                      <TableCell align="right">Impact</TableCell>
                      <TableCell align="right">Confidence</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {decisionResult.decision_recommendation.recommended_actions.map((action) => (
                      <TableRow key={action.action_id}>
                        <TableCell>
                          <Chip label={`#${action.priority}`} size="small" color="primary" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">{action.entity_name}</Typography>
                          <Typography variant="caption" color="text.secondary">{action.entity_type}</Typography>
                        </TableCell>
                        <TableCell>{action.description}</TableCell>
                        <TableCell align="right">{formatCurrency(action.current_value)}</TableCell>
                        <TableCell align="right">{formatCurrency(action.recommended_value)}</TableCell>
                        <TableCell align="right">
                          <Typography color={action.delta >= 0 ? 'success.main' : 'error.main'}>
                            {action.delta >= 0 ? '+' : ''}{formatCurrency(action.delta)}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{formatCurrency(action.expected_impact)}</TableCell>
                        <TableCell align="right">
                          <LinearProgress
                            variant="determinate"
                            value={action.confidence * 100}
                            sx={{ width: 60, display: 'inline-block' }}
                          />
                          <Typography variant="caption" ml={1}>
                            {(action.confidence * 100).toFixed(0)}%
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Supporting Evidence */}
              <Typography variant="subtitle1" fontWeight="bold" mb={1}>
                Supporting Evidence
              </Typography>
              <Grid container spacing={2} mb={3}>
                {decisionResult.decision_recommendation.supporting_evidence.map((evidence) => (
                  <Grid item xs={12} sm={6} md={3} key={evidence.evidence_id}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box display="flex" alignItems="center" gap={1} mb={1}>
                          <InfoIcon color="info" fontSize="small" />
                          <Typography variant="subtitle2">{evidence.title}</Typography>
                        </Box>
                        <Typography variant="body2" color="text.secondary" mb={1}>
                          {evidence.description}
                        </Typography>
                        <Typography variant="h6" color="primary.main">
                          {typeof evidence.metric_value === 'number' && evidence.metric_value < 1
                            ? `${(evidence.metric_value * 100).toFixed(0)}%`
                            : evidence.metric_value.toFixed(2)}
                        </Typography>
                        {evidence.confidence_interval && (
                          <Typography variant="caption" color="text.secondary">
                            CI: [{evidence.confidence_interval[0].toFixed(2)}, {evidence.confidence_interval[1].toFixed(2)}]
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {/* Reasoning Chain */}
              <Typography variant="subtitle1" fontWeight="bold" mb={1}>
                Reasoning Chain
              </Typography>
              <Card sx={{ mb: 3, p: 2 }}>
                <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
                  <Typography variant="caption" color="text.secondary">Crews involved:</Typography>
                  {decisionResult.decision_recommendation.reasoning_chain.crews_involved.map((crew) => (
                    <Chip key={crew} label={crew.replace(/_/g, ' ')} size="small" variant="outlined" />
                  ))}
                </Box>
                <Divider sx={{ mb: 2 }} />
                {decisionResult.decision_recommendation.reasoning_chain.steps.map((step, index) => (
                  <Box key={step.step_id} display="flex" alignItems="flex-start" gap={2} mb={2}>
                    <Box
                      sx={{
                        width: 32,
                        height: 32,
                        borderRadius: '50%',
                        bgcolor: 'primary.main',
                        color: 'white',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      {step.step_number}
                    </Box>
                    <Box flex={1}>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="subtitle2">{step.action}</Typography>
                        <Chip label={step.crew_id.replace(/_/g, ' ')} size="small" />
                      </Box>
                      <Typography variant="body2" color="text.secondary">
                        {step.reasoning}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Output: {step.output_summary}
                      </Typography>
                    </Box>
                    {index < (decisionResult.decision_recommendation?.reasoning_chain.steps.length ?? 0) - 1 && (
                      <ArrowIcon color="action" sx={{ alignSelf: 'center' }} />
                    )}
                  </Box>
                ))}
              </Card>

              {/* Risk Assessment */}
              <Typography variant="subtitle1" fontWeight="bold" mb={1}>
                Risk Assessment
              </Typography>
              <Alert
                severity={decisionResult.decision_recommendation.risk_assessment.includes('LOW') ? 'success' : 
                         decisionResult.decision_recommendation.risk_assessment.includes('MODERATE') ? 'warning' : 'error'}
                icon={<WarningIcon />}
              >
                {decisionResult.decision_recommendation.risk_assessment}
              </Alert>
            </Box>
          )}

          {/* Empty State */}
          {!scenariosData?.scenarios?.length && !loading && (
            <Alert severity="info">
              No scenarios available. Ensure the backend API is running and scenarios are configured.
            </Alert>
          )}
        </Box>
      )}

      {/* Recommendations Tab */}
      {tabValue === 4 && (
        <Box>
          {/* Recommendations Header - Outcomes Focus */}
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 2, 
            mb: 3,
            p: 3,
            background: 'linear-gradient(135deg, #1565C0 0%, #0D47A1 100%)',
            borderRadius: 2,
            color: 'white'
          }}>
            <Box sx={{ 
              width: 56, 
              height: 56, 
              borderRadius: 2, 
              bgcolor: 'rgba(255,255,255,0.2)', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <RevenueIcon sx={{ fontSize: 28 }} />
            </Box>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="h5" fontWeight="bold">Agent Recommendations</Typography>
                <Chip 
                  label="OUTCOMES VIEW" 
                  size="small" 
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 'bold',
                    fontSize: '0.65rem',
                    letterSpacing: '0.05em'
                  }} 
                />
              </Box>
              <Typography variant="body2" sx={{ opacity: 0.9, mt: 0.5 }}>
                Quantified budget allocations with expected impact and confidence scores
              </Typography>
            </Box>
            <IconButton 
              onClick={fetchAgentRecommendations} 
              disabled={loadingRecommendations}
              sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.1)', '&:hover': { bgcolor: 'rgba(255,255,255,0.2)' } }}
            >
              <RefreshIcon />
            </IconButton>
          </Box>

          {loadingRecommendations && (
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress />
            </Box>
          )}

          {agentRecommendations && !loadingRecommendations && (
            <>
              {/* Executive Summary Card */}
              <Card sx={{ mb: 3, bgcolor: 'primary.main', color: 'white' }}>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2} mb={2}>
                    <DecisionIcon fontSize="large" />
                    <Box>
                      <Typography variant="h6">Executive Summary</Typography>
                      <Typography variant="caption">
                        Scenario: {agentRecommendations.scenario_name} | Crews: {agentRecommendations.crews_executed?.join(', ')}
                      </Typography>
                    </Box>
                  </Box>
                  <Typography variant="body1">
                    {agentRecommendations.executive_summary}
                  </Typography>
                  <Box display="flex" gap={3} mt={2}>
                    <Box>
                      <Typography variant="caption">Expected Impact</Typography>
                      <Typography variant="h6">{formatCurrency(agentRecommendations.total_expected_impact || 0)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption">Confidence</Typography>
                      <Typography variant="h6">{((agentRecommendations.overall_confidence || 0) * 100).toFixed(0)}%</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption">Execution Time</Typography>
                      <Typography variant="h6">{agentRecommendations.execution_time_ms}ms</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>

              {/* Dashboard Grid - Brand, RMN, Channel, Campaign */}
              <Grid container spacing={3}>
                {/* Brand Recommendations */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Box sx={{ bgcolor: '#4CAF50', borderRadius: 1, p: 1, display: 'flex' }}>
                          <CrewIcon sx={{ color: 'white' }} />
                        </Box>
                        <Typography variant="h6">Brand Recommendations</Typography>
                      </Box>
                      <Divider sx={{ mb: 2 }} />
                      {agentRecommendations.aggregated_recommendations
                        ?.filter((r: any) => r.entity_type === 'brand')
                        .map((rec: any) => (
                          <Box key={rec.action_id} sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                              <Typography variant="subtitle1" fontWeight="bold">{rec.entity_name}</Typography>
                              <Chip 
                                label={rec.action === 'increase' ? `+${rec.delta_pct?.toFixed(1)}%` : `${rec.delta_pct?.toFixed(1)}%`}
                                color={rec.action === 'increase' ? 'success' : 'warning'}
                                size="small"
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Current</Typography>
                              <Typography variant="body2">{formatCurrency(rec.current_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Recommended</Typography>
                              <Typography variant="body2" fontWeight="bold">{formatCurrency(rec.recommended_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Expected Impact</Typography>
                              <Typography variant="body2" color="success.main">{formatCurrency(rec.expected_impact)}</Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={rec.confidence * 100} 
                              sx={{ mt: 1, mb: 0.5, height: 6, borderRadius: 1 }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {(rec.confidence * 100).toFixed(0)}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary" mt={1} fontSize="0.75rem">
                              {rec.rationale}
                            </Typography>
                          </Box>
                        ))}
                      {!agentRecommendations.aggregated_recommendations?.filter((r: any) => r.entity_type === 'brand').length && (
                        <Typography variant="body2" color="text.secondary" textAlign="center" py={2}>
                          No brand-level recommendations
                        </Typography>
                      )}
                    </CardContent>
                  </Card>
                </Grid>

                {/* RMN Recommendations */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Box sx={{ bgcolor: '#2196F3', borderRadius: 1, p: 1, display: 'flex' }}>
                          <PeopleIcon sx={{ color: 'white' }} />
                        </Box>
                        <Typography variant="h6">Retail Media Network Recommendations</Typography>
                      </Box>
                      <Divider sx={{ mb: 2 }} />
                      {agentRecommendations.aggregated_recommendations
                        ?.filter((r: any) => r.entity_type === 'rmn')
                        .map((rec: any) => (
                          <Box key={rec.action_id} sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                              <Typography variant="subtitle1" fontWeight="bold">{rec.entity_name}</Typography>
                              <Chip 
                                label={rec.action === 'increase' ? `+${rec.delta_pct?.toFixed(1)}%` : `${rec.delta_pct?.toFixed(1)}%`}
                                color={rec.action === 'increase' ? 'success' : 'warning'}
                                size="small"
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Current</Typography>
                              <Typography variant="body2">{formatCurrency(rec.current_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Recommended</Typography>
                              <Typography variant="body2" fontWeight="bold">{formatCurrency(rec.recommended_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Expected Impact</Typography>
                              <Typography variant="body2" color="success.main">{formatCurrency(rec.expected_impact)}</Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={rec.confidence * 100} 
                              sx={{ mt: 1, mb: 0.5, height: 6, borderRadius: 1 }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {(rec.confidence * 100).toFixed(0)}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary" mt={1} fontSize="0.75rem">
                              {rec.rationale}
                            </Typography>
                          </Box>
                        ))}
                      {!agentRecommendations.aggregated_recommendations?.filter((r: any) => r.entity_type === 'rmn').length && (
                        <Typography variant="body2" color="text.secondary" textAlign="center" py={2}>
                          No RMN-level recommendations
                        </Typography>
                      )}
                    </CardContent>
                  </Card>
                </Grid>

                {/* Channel Recommendations */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Box sx={{ bgcolor: '#9C27B0', borderRadius: 1, p: 1, display: 'flex' }}>
                          <CategoryIcon sx={{ color: 'white' }} />
                        </Box>
                        <Typography variant="h6">Channel Recommendations</Typography>
                      </Box>
                      <Divider sx={{ mb: 2 }} />
                      {agentRecommendations.aggregated_recommendations
                        ?.filter((r: any) => r.entity_type === 'channel')
                        .map((rec: any) => (
                          <Box key={rec.action_id} sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                              <Typography variant="subtitle1" fontWeight="bold">{rec.entity_name}</Typography>
                              <Chip 
                                label={rec.action === 'increase' ? `+${rec.delta_pct?.toFixed(1)}%` : `${rec.delta_pct?.toFixed(1)}%`}
                                color={rec.action === 'increase' ? 'success' : 'warning'}
                                size="small"
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Current</Typography>
                              <Typography variant="body2">{formatCurrency(rec.current_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Recommended</Typography>
                              <Typography variant="body2" fontWeight="bold">{formatCurrency(rec.recommended_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Expected Impact</Typography>
                              <Typography variant="body2" color="success.main">{formatCurrency(rec.expected_impact)}</Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={rec.confidence * 100} 
                              sx={{ mt: 1, mb: 0.5, height: 6, borderRadius: 1 }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {(rec.confidence * 100).toFixed(0)}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary" mt={1} fontSize="0.75rem">
                              {rec.rationale}
                            </Typography>
                          </Box>
                        ))}
                      {!agentRecommendations.aggregated_recommendations?.filter((r: any) => r.entity_type === 'channel').length && (
                        <Typography variant="body2" color="text.secondary" textAlign="center" py={2}>
                          No channel-level recommendations
                        </Typography>
                      )}
                    </CardContent>
                  </Card>
                </Grid>

                {/* Campaign Recommendations */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Box sx={{ bgcolor: '#FF9800', borderRadius: 1, p: 1, display: 'flex' }}>
                          <SpeedIcon sx={{ color: 'white' }} />
                        </Box>
                        <Typography variant="h6">Campaign Recommendations</Typography>
                      </Box>
                      <Divider sx={{ mb: 2 }} />
                      {agentRecommendations.aggregated_recommendations
                        ?.filter((r: any) => r.entity_type === 'campaign')
                        .map((rec: any) => (
                          <Box key={rec.action_id} sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                              <Typography variant="subtitle1" fontWeight="bold">{rec.entity_name}</Typography>
                              <Chip 
                                label={rec.action === 'increase' ? `+${rec.delta_pct?.toFixed(1)}%` : `${rec.delta_pct?.toFixed(1)}%`}
                                color={rec.action === 'increase' ? 'success' : 'warning'}
                                size="small"
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Current</Typography>
                              <Typography variant="body2">{formatCurrency(rec.current_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Recommended</Typography>
                              <Typography variant="body2" fontWeight="bold">{formatCurrency(rec.recommended_value)}</Typography>
                            </Box>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2" color="text.secondary">Expected Impact</Typography>
                              <Typography variant="body2" color="success.main">{formatCurrency(rec.expected_impact)}</Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={rec.confidence * 100} 
                              sx={{ mt: 1, mb: 0.5, height: 6, borderRadius: 1 }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {(rec.confidence * 100).toFixed(0)}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary" mt={1} fontSize="0.75rem">
                              {rec.rationale}
                            </Typography>
                          </Box>
                        ))}
                      {!agentRecommendations.aggregated_recommendations?.filter((r: any) => r.entity_type === 'campaign').length && (
                        <Typography variant="body2" color="text.secondary" textAlign="center" py={2}>
                          No campaign-level recommendations
                        </Typography>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              {/* Crew Evidence Section */}
              <Typography variant="h6" mt={4} mb={2}>
                Supporting Evidence by Crew
              </Typography>
              <Grid container spacing={2}>
                {agentRecommendations.supporting_evidence?.map((evidence: any, index: number) => (
                  <Grid item xs={12} md={4} key={index}>
                    <Card>
                      <CardContent>
                        <Box display="flex" alignItems="center" gap={1} mb={2}>
                          <CheckIcon color="success" />
                          <Typography variant="subtitle1" fontWeight="bold">
                            {evidence.source?.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                          </Typography>
                        </Box>
                        <Box mb={2}>
                          <Typography variant="caption" color="text.secondary">Findings</Typography>
                          {evidence.findings?.map((finding: string, i: number) => (
                            <Typography key={i} variant="body2" display="flex" alignItems="center" gap={0.5}>
                              • {finding}
                            </Typography>
                          ))}
                        </Box>
                        <Box mb={2}>
                          <Typography variant="caption" color="text.secondary">Opportunities</Typography>
                          {evidence.opportunities?.map((opp: string, i: number) => (
                            <Typography key={i} variant="body2" color="success.main" display="flex" alignItems="center" gap={0.5}>
                              <RevenueIcon fontSize="small" /> {opp}
                            </Typography>
                          ))}
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary">Risks</Typography>
                          {evidence.risks?.map((risk: string, i: number) => (
                            <Typography key={i} variant="body2" color="warning.main" display="flex" alignItems="center" gap={0.5}>
                              <WarningIcon fontSize="small" /> {risk}
                            </Typography>
                          ))}
                        </Box>
                        <Box mt={2}>
                          <LinearProgress 
                            variant="determinate" 
                            value={(evidence.confidence || 0) * 100}
                            sx={{ height: 8, borderRadius: 1 }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            Crew Confidence: {((evidence.confidence || 0) * 100).toFixed(0)}%
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {/* Risk Assessment */}
              <Box mt={4}>
                <Typography variant="h6" mb={2}>Risk Assessment</Typography>
                <Alert 
                  severity={agentRecommendations.risk_assessment?.includes('LOW') ? 'success' : 
                           agentRecommendations.risk_assessment?.includes('MODERATE') ? 'warning' : 'error'}
                  icon={<ShieldIcon />}
                >
                  <Typography variant="body2">{agentRecommendations.risk_assessment}</Typography>
                </Alert>
              </Box>
            </>
          )}

          {/* Empty State */}
          {!agentRecommendations && !loadingRecommendations && (
            <Card sx={{ p: 4, textAlign: 'center' }}>
              <DecisionIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
              <Typography variant="h6" gutterBottom>No Recommendations Available</Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Click the refresh button to generate agent recommendations based on current performance data.
              </Typography>
              <IconButton onClick={fetchAgentRecommendations} color="primary" size="large">
                <RefreshIcon fontSize="large" />
              </IconButton>
            </Card>
          )}
        </Box>
      )}
    </Box>
  );
};

export default OptimizationCrewsPage;
