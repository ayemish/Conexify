import { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Send,
  X,
  Minimize2,
  Maximize2,
  Bot,
  User,
  Loader2,
  Sparkles,
  Lightbulb,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';
import { advisorApi } from '../services/advisorApi';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  data?: Record<string, unknown>;
  scenarioIds?: string[];
  confidence?: number;
}

interface ScenarioAdvisorChatProps {
  ecosystem?: 'rmn' | 'demand_procurement' | 'auto';
  defaultOpen?: boolean;
}

export function ScenarioAdvisorChat({ 
  ecosystem = 'auto',
  defaultOpen = false 
}: ScenarioAdvisorChatProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedEcosystem, setSelectedEcosystem] = useState(ecosystem);
  const [error, setError] = useState<string | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && !sessionId) {
      initializeSession();
    }
  }, [isOpen]);

  const initializeSession = async () => {
    try {
      setError(null);
      const session = await advisorApi.createSession(selectedEcosystem);
      setSessionId(session.session_id);
      
      // Add welcome message
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: session.message || getWelcomeMessage(),
        timestamp: new Date(),
      }]);
    } catch (err) {
      console.error('Failed to create session:', err);
      setError('Failed to connect to advisor. Please try again.');
      // Add offline welcome message
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: getWelcomeMessage(),
        timestamp: new Date(),
      }]);
    }
  };

  const getWelcomeMessage = () => {
    if (selectedEcosystem === 'rmn') {
      return `👋 Hi! I'm your RMN Scenario Advisor. I can help you with:

• **Media spend optimization** across channels
• **ROAS analysis** and improvement strategies  
• **Scenario recommendations** (Grow Revenue, Maintain Stability, etc.)
• **Incrementality insights** and attribution

What would you like to explore?`;
    } else if (selectedEcosystem === 'demand_procurement') {
      return `👋 Hi! I'm your Demand & Procurement Advisor. I can help you with:

• **Demand forecasting** for SKUs
• **Inventory optimization** (safety stock, reorder points)
• **Stockout risk assessment**
• **Procurement planning** recommendations

What would you like to analyze?`;
    }
    return `👋 Hi! I'm your Scenario Advisory Assistant. I can help with:

**RMN (Retail Media)**
• Channel optimization & budget allocation
• ROAS and incrementality analysis

**Demand & Procurement**  
• Demand forecasting & inventory optimization
• Stockout risk & procurement planning

Which area would you like to explore?`;
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError(null);

    try {
      if (!sessionId) {
        await initializeSession();
      }

      const result = await advisorApi.sendMessage(sessionId!, userMessage.content);
      const response = result.response;

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.message,
        timestamp: new Date(),
        data: response.data || undefined,
        scenarioIds: response.scenario_ids,
        confidence: response.confidence,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Failed to send message:', err);
      
      // Provide mock response when backend is unavailable
      const mockResponse = getMockResponse(userMessage.content);
      setMessages(prev => [...prev, {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: mockResponse,
        timestamp: new Date(),
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const getMockResponse = (input: string): string => {
    const lower = input.toLowerCase();
    
    if (lower.includes('scenario') || lower.includes('recommend')) {
      return `Based on your query, here are some relevant scenarios:

**For RMN:**
• **Grow Revenue for Brand** - Maximize incremental sales
• **Maximize ROAS** - Efficiency optimization
• **Maintain Revenue** - Stability mode

**For Demand & Procurement:**
• **Baseline** - Current policy evaluation
• **Conservative** - Higher safety stock

Which scenario would you like to explore in detail?`;
    }
    
    if (lower.includes('stockout') || lower.includes('risk')) {
      return `I can analyze stockout risk for your inventory. Key factors I consider:

• **Current inventory levels** vs reorder point
• **Demand variability** and forecast accuracy
• **Lead time uncertainty**
• **Service level targets**

Please specify a SKU ID to get a detailed risk assessment.`;
    }
    
    if (lower.includes('forecast') || lower.includes('demand')) {
      return `Our demand forecasting approach includes:

• **Historical patterns** analysis
• **Seasonality** adjustments
• **Promotional impact** modeling
• **Endogenous factors** (basket dynamics)

Would you like a forecast for a specific SKU?`;
    }

    return `I can help you with scenario optimization. Try asking about:

• "What scenario fits my goal of growing revenue?"
• "Assess stockout risk for SKU-001"
• "Generate a demand forecast"
• "Compare conservative vs baseline scenarios"

What would you like to explore?`;
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewSession = async () => {
    setSessionId(null);
    setMessages([]);
    await initializeSession();
  };

  const quickActions = [
    { label: 'RMN Scenarios', query: 'What RMN scenarios are available?' },
    { label: 'Stockout Risk', query: 'Assess stockout risk for my inventory' },
    { label: 'Demand Forecast', query: 'Generate a demand forecast' },
    { label: 'Compare Scenarios', query: 'Compare baseline vs conservative scenario' },
  ];

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-br from-indigo-600 to-purple-700 rounded-full shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center group z-50"
      >
        <MessageSquare className="w-6 h-6 text-white group-hover:scale-110 transition-transform" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white animate-pulse"></span>
      </button>
    );
  }

  return (
    <div
      className={`fixed bottom-6 right-6 bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col z-50 transition-all duration-300 ${
        isMinimized ? 'w-80 h-14' : 'w-96 h-[600px]'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-indigo-600 to-purple-700 rounded-t-2xl">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-white/20 rounded-lg flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-white font-semibold text-sm">Scenario Advisor</h3>
            {!isMinimized && (
              <p className="text-white/70 text-xs">AI-powered insights</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
          >
            {isMinimized ? (
              <Maximize2 className="w-4 h-4 text-white" />
            ) : (
              <Minimize2 className="w-4 h-4 text-white" />
            )}
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>

      {!isMinimized && (
        <>
          {/* Ecosystem Selector */}
          <div className="px-4 py-2 border-b border-slate-100 bg-slate-50">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Domain:</span>
              <select
                value={selectedEcosystem}
                onChange={(e) => {
                  setSelectedEcosystem(e.target.value as typeof selectedEcosystem);
                  handleNewSession();
                }}
                className="text-xs bg-white border border-slate-200 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="auto">Auto-detect</option>
                <option value="rmn">Retail Media (RMN)</option>
                <option value="demand_procurement">Demand & Procurement</option>
              </select>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {message.role === 'assistant' && (
                  <div className="w-7 h-7 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <Bot className="w-4 h-4 text-indigo-600" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                    message.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-md'
                      : 'bg-slate-100 text-slate-800 rounded-bl-md'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  {message.confidence !== undefined && message.confidence > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-200/50 flex items-center gap-1">
                      {message.confidence > 0.8 ? (
                        <CheckCircle className="w-3 h-3 text-green-500" />
                      ) : (
                        <AlertCircle className="w-3 h-3 text-amber-500" />
                      )}
                      <span className="text-xs text-slate-500">
                        {Math.round(message.confidence * 100)}% confidence
                      </span>
                    </div>
                  )}
                </div>
                {message.role === 'user' && (
                  <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center flex-shrink-0">
                    <User className="w-4 h-4 text-white" />
                  </div>
                )}
              </div>
            ))}
            
            {isLoading && (
              <div className="flex gap-2 justify-start">
                <div className="w-7 h-7 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-indigo-600" />
                </div>
                <div className="bg-slate-100 rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />
                    <span className="text-sm text-slate-500">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Actions */}
          {messages.length <= 1 && (
            <div className="px-4 py-2 border-t border-slate-100">
              <p className="text-xs text-slate-500 mb-2 flex items-center gap-1">
                <Lightbulb className="w-3 h-3" /> Quick actions
              </p>
              <div className="flex flex-wrap gap-1.5">
                {quickActions.map((action, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInputValue(action.query);
                      inputRef.current?.focus();
                    }}
                    className="text-xs px-2.5 py-1.5 bg-slate-100 hover:bg-indigo-100 text-slate-600 hover:text-indigo-700 rounded-full transition-colors"
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="p-3 border-t border-slate-200">
            {error && (
              <div className="mb-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-xs text-red-600">{error}</p>
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask about scenarios..."
                className="flex-1 px-4 py-2.5 bg-slate-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-colors"
                disabled={isLoading}
              />
              <button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isLoading}
                className="w-10 h-10 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 rounded-xl flex items-center justify-center transition-colors"
              >
                <Send className="w-4 h-4 text-white" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default ScenarioAdvisorChat;
