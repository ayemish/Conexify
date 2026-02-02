import { useNavigate } from 'react-router-dom';
import { 
  Wrench, 
  Brain, 
  Activity, 
  Shield, 
  BarChart3, 
  Bell,
  ArrowRight,
  CheckCircle2,
  Zap,
  RefreshCw
} from 'lucide-react';

const features = [
  {
    icon: Brain,
    title: 'ML-Powered Predictions',
    description: 'Advanced anomaly detection and failure prediction using state-of-the-art machine learning models.',
  },
  {
    icon: Activity,
    title: 'Real-Time Monitoring',
    description: 'Continuous monitoring of equipment health with instant alerts and notifications.',
  },
  {
    icon: RefreshCw,
    title: 'Automated Retraining',
    description: 'Self-improving models with automated retraining pipelines triggered by drift detection.',
  },
  {
    icon: Shield,
    title: 'Governance & Compliance',
    description: 'Full audit trails, approval workflows, and risk assessment for model deployments.',
  },
  {
    icon: BarChart3,
    title: 'A/B Testing Framework',
    description: 'Compare model performance with controlled experiments and statistical analysis.',
  },
  {
    icon: Bell,
    title: 'Smart Alerting',
    description: 'Configurable alert rules with multi-channel notifications (Email, Slack, Webhook).',
  },
];

const stats = [
  { value: '99.2%', label: 'Prediction Accuracy' },
  { value: '45%', label: 'Maintenance Cost Reduction' },
  { value: '72hrs', label: 'Avg. Early Warning' },
  { value: '24/7', label: 'Continuous Monitoring' },
];

export function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-900/80 backdrop-blur-sm border-b border-slate-800 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-600 rounded-lg flex items-center justify-center">
              <Wrench className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold text-white">Arctic Pulse</span>
          </div>
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate('/login')}
              className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
            >
              Sign In
            </button>
            <button 
              onClick={() => navigate('/login')}
              className="px-5 py-2 bg-gradient-to-r from-orange-500 to-red-600 text-white font-medium rounded-lg hover:from-orange-600 hover:to-red-700 transition-all"
            >
              Get Started
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-orange-600/20 via-transparent to-red-600/20"></div>
        <div className="max-w-7xl mx-auto px-6 py-24 relative">
          <div className="text-center max-w-4xl mx-auto">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-orange-500/10 border border-orange-500/30 rounded-full mb-6">
              <Zap className="w-4 h-4 text-orange-400" />
              <span className="text-orange-300 text-sm font-medium">AI-Powered Predictive Maintenance</span>
            </div>
            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6 leading-tight">
              Predict Equipment Failures
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-red-400">
                Before They Happen
              </span>
            </h1>
            <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto">
              Leverage machine learning to detect anomalies, predict failures, and optimize maintenance schedules for HVACR systems in Oil & Gas operations.
            </p>
            <div className="flex items-center justify-center gap-4">
              <button 
                onClick={() => navigate('/login')}
                className="px-8 py-4 bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold rounded-xl hover:from-orange-600 hover:to-red-700 transition-all flex items-center gap-2 shadow-lg shadow-orange-500/30"
              >
                Start Free Trial
                <ArrowRight className="w-5 h-5" />
              </button>
              <button className="px-8 py-4 bg-slate-800 text-white font-semibold rounded-xl hover:bg-slate-700 transition-colors border border-slate-700">
                Watch Demo
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 border-y border-slate-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-red-400 mb-2">
                  {stat.value}
                </p>
                <p className="text-slate-400">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Comprehensive ML Operations Platform
            </h2>
            <p className="text-xl text-slate-400 max-w-2xl mx-auto">
              Everything you need to build, deploy, and manage predictive maintenance models at scale.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature) => (
              <div 
                key={feature.title}
                className="p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:border-orange-500/50 transition-colors group"
              >
                <div className="w-12 h-12 bg-gradient-to-br from-orange-500/20 to-red-500/20 rounded-xl flex items-center justify-center mb-4 group-hover:from-orange-500/30 group-hover:to-red-500/30 transition-colors">
                  <feature.icon className="w-6 h-6 text-orange-400" />
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-slate-400">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 bg-gradient-to-br from-orange-600/10 to-red-600/10">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Ready to Reduce Unplanned Downtime?
          </h2>
          <p className="text-xl text-slate-400 mb-8">
            Join leading Oil & Gas operators who trust our ML-powered predictive maintenance platform.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-8">
            <button 
              onClick={() => navigate('/login')}
              className="px-8 py-4 bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold rounded-xl hover:from-orange-600 hover:to-red-700 transition-all flex items-center gap-2"
            >
              Get Started Now
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
          <div className="flex items-center justify-center gap-6 text-slate-400">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
              Free 14-day trial
            </span>
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
              No credit card required
            </span>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-orange-500 to-red-600 rounded-lg flex items-center justify-center">
                <Wrench className="w-4 h-4 text-white" />
              </div>
              <span className="text-lg font-bold text-white">Arctic Pulse</span>
            </div>
            <p className="text-slate-500 text-sm">
              © 2026 Arctic Pulse Predictive Maintenance System. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
