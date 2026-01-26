import { useNavigate } from 'react-router-dom';
import { 
  TrendingUp, 
  ArrowRight,
  Package,
  DollarSign,
  BarChart3,
  Target,
  Layers
} from 'lucide-react';

interface PlaybookCard {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  icon: React.ElementType;
  accentColor: string;
  bgGradient: string;
  route: string;
  features: string[];
  metrics: { label: string; value: string }[];
}

const playbooks: PlaybookCard[] = [
  {
    id: 'demand-procurement',
    title: 'Demand Forecasting Impact on Procurement & Inventory',
    subtitle: 'Inventory Optimization',
    description: 'Optimize inventory levels, forecast demand, and generate procurement plans using probabilistic forecasting and risk analysis.',
    icon: Package,
    accentColor: 'emerald',
    bgGradient: 'from-emerald-500 to-teal-600',
    route: '/demand-procurement',
    features: [
      'Probabilistic demand forecasting',
      'Safety stock optimization (ROP/EOQ)',
      'Supplier management & scoring',
      'Risk analysis & mitigation',
      'Procurement plan generation'
    ],
    metrics: [
      { label: 'Service Level', value: '95%+' },
      { label: 'Inventory Turns', value: '12x' },
      { label: 'Stockout Risk', value: '<5%' }
    ]
  },
  {
    id: 'retail-media',
    title: 'Retail Media Optimization',
    subtitle: 'Marketing Spend Allocation',
    description: 'Optimize retail media network spend across retailers and channels using Bayesian inference and Monte Carlo simulation.',
    icon: TrendingUp,
    accentColor: 'indigo',
    bgGradient: 'from-indigo-500 to-purple-600',
    route: '/retail-media',
    features: [
      'Multi-retailer media allocation',
      'Channel elasticity modeling',
      'Federated Bayesian learning',
      'Digital Twin simulation',
      'ROAS optimization'
    ],
    metrics: [
      { label: 'Budget', value: '$10M' },
      { label: 'ROAS', value: '4.5x' },
      { label: 'Retailers', value: '5' }
    ]
  }
];

export function EcosystemSelectPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
              <Layers className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Intelligence Cooperative</h1>
              <p className="text-sm text-slate-400">Business Ecosystem Playbooks</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Hero Section */}
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">
            Select Your Business Ecosystem
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Choose a playbook for ecosystem management for Intelligence Federation → Bayesian → Digital Twin → Agent pipelines.
          </p>
        </div>

        {/* Playbook Cards */}
        <div className="grid md:grid-cols-2 gap-8 mb-12">
          {playbooks.map((playbook) => (
            <div
              key={playbook.id}
              className="group relative bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-2xl overflow-hidden hover:border-slate-600 transition-all duration-300 hover:shadow-2xl hover:shadow-slate-900/50"
            >
              {/* Gradient Header */}
              <div className={`bg-gradient-to-r ${playbook.bgGradient} p-6`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur-sm">
                      <playbook.icon className="w-8 h-8 text-white" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-bold text-white">{playbook.title}</h3>
                      <p className="text-white/80">{playbook.subtitle}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Content */}
              <div className="p-6">
                <p className="text-slate-300 mb-6">{playbook.description}</p>

                {/* Features */}
                <div className="mb-6">
                  <h4 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
                    Key Capabilities
                  </h4>
                  <ul className="space-y-2">
                    {playbook.features.map((feature, idx) => (
                      <li key={idx} className="flex items-center gap-2 text-slate-300">
                        <div className={`w-1.5 h-1.5 rounded-full bg-${playbook.accentColor}-400`} />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  {playbook.metrics.map((metric, idx) => (
                    <div key={idx} className="text-center p-3 bg-slate-700/30 rounded-lg">
                      <p className="text-xl font-bold text-white">{metric.value}</p>
                      <p className="text-xs text-slate-400">{metric.label}</p>
                    </div>
                  ))}
                </div>

                {/* CTA Button */}
                <button
                  onClick={() => navigate(playbook.route)}
                  className={`w-full flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r ${playbook.bgGradient} text-white font-semibold rounded-xl hover:opacity-90 transition-opacity group-hover:shadow-lg`}
                >
                  Launch Playbook
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Architecture Overview */}
        <div className="bg-slate-800/30 border border-slate-700/50 rounded-2xl p-8">
          <h3 className="text-xl font-bold text-white mb-6 text-center">
            Four-Plane Architecture
          </h3>
          <div className="grid md:grid-cols-4 gap-6">
            {[
              { icon: BarChart3, title: 'Bayesian Model', desc: 'Federated posterior inference with uncertainty quantification' },
              { icon: Layers, title: 'Digital Twin', desc: 'Living state simulation with Monte Carlo scenarios' },
              { icon: Target, title: 'Agent Orchestration', desc: 'Multi-agent pipeline with explainable decisions' },
              { icon: DollarSign, title: 'Decision Pack', desc: 'Actionable recommendations with confidence intervals' }
            ].map((plane, idx) => (
              <div key={idx} className="text-center">
                <div className="w-12 h-12 bg-slate-700/50 rounded-xl flex items-center justify-center mx-auto mb-3">
                  <plane.icon className="w-6 h-6 text-blue-400" />
                </div>
                <h4 className="font-semibold text-white mb-1">{plane.title}</h4>
                <p className="text-sm text-slate-400">{plane.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-700/50 mt-12">
        <div className="max-w-7xl mx-auto px-6 py-6 text-center text-slate-500 text-sm">
          Federated Demand Twin — Bayesian → Digital Twin → Agent Pipeline Architecture
        </div>
      </footer>
    </div>
  );
}
