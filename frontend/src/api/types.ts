export interface User {
  id: number;
  name: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface Holding {
  id: number;
  symbol: string;
  quantity: number;
  avg_cost: number;
}

export interface EvidenceItem {
  symbol: string;
  title: string;
  source_url: string;
}

export interface InvestigationResult {
  question: string;
  answer: string;
  trajectory: string[];
  risk_results: Record<string, Record<string, number>>;
  evidence: EvidenceItem[];
  limitations: string | null;
}
