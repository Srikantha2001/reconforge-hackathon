// Mirrors backend/app/schemas.py — kept hand-in-sync deliberately (no
// codegen for a hackathon-scale surface).

export interface Actor {
  id: string
  display_name: string
}

export interface Transform {
  field: string
  op: 'abs' | 'upper' | 'lower' | 'strip' | 'round2'
  side?: 'a' | 'b' | 'both'
}

export interface MatchRule {
  field_a: string
  field_b: string
  type: 'exact' | 'numeric_tolerance' | 'date_tolerance'
  tolerance?: number
  tolerance_days?: number
}

export interface ReconConfigJson {
  recon_name: string
  source_a: { alias: string; key_columns: string[] }
  source_b: { alias: string; key_columns: string[] }
  transforms: Transform[]
  match_rules: MatchRule[]
}

export interface ConfigOut {
  id: number
  recon_name: string
  version: number
  config_json: ReconConfigJson
  english_summary: string | null
  status: 'draft' | 'approved'
  author_id: string | null
  approver_id: string | null
  parent_id: number | null
  origin: 'authoring' | 'loop_a'
  created_at: string
  approved_at: string | null
  repairs_applied: string[]
}

export interface RunOut {
  id: number
  config_id: number
  config_version: number
  matched_count: number
  break_count: number
  total_a: number
  total_b: number
  match_rate: number
  output_hash: string
  actor_id: string | null
  created_at: string
}

export interface ReproducibilityCheckOut {
  run_id: number
  original_hash: string
  recomputed_hash: string
  reproducible: boolean
}

export interface BreakOut {
  id: number
  run_id: number
  break_key: string
  row_a: Record<string, unknown> | null
  row_b: Record<string, unknown> | null
  failed_rules: string[]
  deltas: Record<string, number | null>
  archetype: string | null
  explanation: string | null
  suggested_resolution: string | null
  sme_confidence: number | null
  judge_confidence: number | null
  judge_decision: string | null
  severity: 'low' | 'medium' | 'high'
  status: string
  created_at: string
}

export interface AdviseOut {
  break_id: number
  archetype: string
  label: string
  explanation: string
  suggested_resolution: string
  sme_confidence: number
  judge_decision: 'accept' | 'route_to_human'
  judge_confidence: number
  judge_reason: string
  source: 'resolution_memory' | 'llm' | 'stub'
}

export interface ChaserOut {
  to: string
  subject: string
  body: string
}

export interface LoopAAggregateGroup {
  field_a: string
  field_b: string
  type: string
  observed_deltas: number[]
  count: number
}

export interface LoopAProposeOut {
  new_config: ConfigOut
  rationale: string
}

export interface LoopAWhatIfOut {
  current_match_rate: number
  candidate_match_rate: number
  current_matched: number
  candidate_matched: number
  newly_matched_keys: string[]
  newly_broken_keys: string[]
}

export interface AuditLogOut {
  id: number
  actor_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  agent_reasoning: string | null
  confidence: number | null
  timestamp: string
}

export interface DashboardOut {
  run: RunOut
  archetype_counts: Record<string, number>
  severity_counts: Record<string, number>
  status_counts: Record<string, number>
}

export interface ResolutionMemoryOut {
  id: number
  feature_key: string
  archetype: string
  resolution: string
  confidence: number
  times_seen: number
}

export interface SeedInfo {
  exists: boolean
  ledger_columns: string[]
  statement_columns: string[]
}

export const ARCHETYPE_LABELS: Record<string, string> = {
  value_date_mismatch: 'Value-date mismatch',
  fx_rounding_diff: 'FX rounding / conversion diff',
  partial_fill: 'Partial fill / quantity mismatch',
  duplicate_entry: 'Duplicate entry',
  fee_charge_diff: 'Fee / charge difference',
  timing_settlement_lag: 'Timing / settlement lag (one-sided)',
  wrong_account_reference: 'Wrong account / reference',
  missing_counterparty_leg: 'Missing counterparty leg',
  amount_outside_tolerance: 'Amount outside tolerance',
  reference_format_mismatch: 'Reference / ID format mismatch',
}
