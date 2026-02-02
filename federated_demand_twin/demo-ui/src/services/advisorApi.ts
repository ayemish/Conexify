/**
 * API Service for Scenario Advisor Chat
 */

const API_BASE_URL = 'http://localhost:8000';

export interface AdvisorMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface AdvisorResponse {
  message: string;
  ecosystem: string | null;
  scenario_ids: string[];
  data: Record<string, unknown> | null;
  actions: Array<{ type: string; label: string }>;
  confidence: number;
  timestamp: string;
}

export interface AdvisorSession {
  session_id: string;
  created_at: string;
  ecosystem: string;
  message?: string;
}

export interface Scenario {
  scenario_id: string;
  name: string;
  description: string;
  category?: string;
  objective_type?: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
}

export interface AdvisorStatus {
  status: string;
  openai_available: boolean;
  model: string | null;
  active_sessions: number;
  ecosystems: string[];
}

class AdvisorApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  async createSession(ecosystem: string = 'auto'): Promise<AdvisorSession> {
    const response = await fetch(`${this.baseUrl}/api/advisor/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ecosystem }),
    });
    
    if (!response.ok) {
      throw new Error(`Failed to create session: ${response.statusText}`);
    }
    
    return response.json();
  }

  async sendMessage(sessionId: string, message: string, stream: boolean = false): Promise<{
    session_id: string;
    response: AdvisorResponse;
  }> {
    const response = await fetch(`${this.baseUrl}/api/advisor/chat/${sessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, stream }),
    });
    
    if (!response.ok) {
      throw new Error(`Failed to send message: ${response.statusText}`);
    }
    
    return response.json();
  }

  async getHistory(sessionId: string): Promise<{
    session_id: string;
    ecosystem: string;
    messages: AdvisorMessage[];
    context: Record<string, unknown>;
  }> {
    const response = await fetch(`${this.baseUrl}/api/advisor/chat/${sessionId}/history`);
    
    if (!response.ok) {
      throw new Error(`Failed to get history: ${response.statusText}`);
    }
    
    return response.json();
  }

  async deleteSession(sessionId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/advisor/chat/${sessionId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      throw new Error(`Failed to delete session: ${response.statusText}`);
    }
  }

  async getScenarios(ecosystem: string): Promise<{
    ecosystem: string;
    scenarios: Scenario[];
    categories: string[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/advisor/scenarios/${ecosystem}`);
    
    if (!response.ok) {
      throw new Error(`Failed to get scenarios: ${response.statusText}`);
    }
    
    return response.json();
  }

  async getAgents(ecosystem: string): Promise<{
    ecosystem: string;
    agents: Agent[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/advisor/agents/${ecosystem}`);
    
    if (!response.ok) {
      throw new Error(`Failed to get agents: ${response.statusText}`);
    }
    
    return response.json();
  }

  async getStatus(): Promise<AdvisorStatus> {
    const response = await fetch(`${this.baseUrl}/api/advisor/status`);
    
    if (!response.ok) {
      throw new Error(`Failed to get status: ${response.statusText}`);
    }
    
    return response.json();
  }
}

export const advisorApi = new AdvisorApiService();
