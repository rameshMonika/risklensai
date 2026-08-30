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
  evidence_text: string | null;
}

export interface ConcentrationResult {
  weights: Record<string, number>;
  largest_holding_symbol: string;
  largest_holding_weight: number;
}

export interface InvestigationResult {
  question: string;
  answer: string;
  status: "completed" | "refused" | "not_found";
  trajectory: string[];
  risk_results: Record<string, Record<string, number>>;
  concentration: ConcentrationResult | null;
  correlation_matrix: Record<string, Record<string, number>> | null;
  evidence: EvidenceItem[];
  limitations: string | null;
}


export interface SymbolSearchResult {
  symbol: string;
  name: string;
}

export interface Quote {
  symbol: string;
  price: number;
}
