export interface TranscriptTurn {
  agent: string;
  vote: string;
  rationale: string;
}

export interface DebateSummary {
  debate_id: string;
  symbol: string;
  ts: string;
  final_decision: string;
  votes: Record<string, string>;
  pyth_gate: string | null;
  shapley_top_agent: string | null;
}

export interface PythBlock {
  price: number;
  conf: number;
  conf_pct?: number | null;
  staleness_s?: number | null;
  feed?: string | null;
}

export interface DebateDetail extends DebateSummary {
  transcript: TranscriptTurn[];
  pyth_price: PythBlock | null;
  jupiter_quote: Record<string, unknown> | null;
  dry_run_signature: string | null;
  shapley_weights: Record<string, number> | null;
  shapley_rationale: string | null;
  shapley_rolling_weights: Record<string, number> | null;
}

export interface ShapleyPoint {
  ts: string | null;
  weights: Record<string, number>;
}

export interface ShapleyHistoryResponse {
  k: number;
  points: ShapleyPoint[];
}

export interface RunnerMetrics {
  total: number;
  success: number;
  errors: number;
  rate_limit_errors: number;
  parse_failures: number;
  retries: number;
  pyth_gate_holds: number;
  jupiter_quotes_attached: number;
  dry_run_built: number;
  shapley_attached: number;
  success_rate: number;
  avg_latency: number;
  p95_latency: number;
  recent_errors: Array<Record<string, unknown>>;
}

export interface Stats {
  total: number;
  success: number;
  errors: number;
  parse_failures: number;
  pyth_gate_holds: number;
  shapley_attached: number;
  jupiter_quotes_attached: number;
  dry_run_built: number;
  success_rate: number;
  avg_latency: number;
  p95_latency: number;
  debates_count: number;
  shapley_rows: number;
  tests_passing: number;
  git_sha: string | null;
}

export interface PayoutLatest {
  payout: Record<string, unknown> | null;
  message: string;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { headers: { accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`GET /api${path} → ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  getStats: () => fetchJson<Stats>("/stats"),
  getRunnerMetrics: () => fetchJson<RunnerMetrics>("/runner/metrics"),
  getRecentDebates: (limit = 20) => fetchJson<DebateSummary[]>(`/debates/recent?limit=${limit}`),
  getDebate: (id: string) => fetchJson<DebateDetail>(`/debates/${encodeURIComponent(id)}`),
  getShapleyLeaderboard: () => fetchJson<ShapleyPoint>("/shapley/leaderboard"),
  getShapleyHistory: (k = 10, limit = 100) =>
    fetchJson<ShapleyHistoryResponse>(`/shapley/history?k=${k}&limit=${limit}`),
  getPayoutLatest: () => fetchJson<PayoutLatest>("/payout/latest"),
};
