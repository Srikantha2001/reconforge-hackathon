// v2 types — mirror backend/app/schemas.py (hand-synced, no codegen).

export interface AuthUser {
  user_id: string
  email: string
  name: string
  role: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  role: string
  email: string
  name: string
}

export interface ConfigOut {
  id: number
  recon_name: string
  recon_type: string
  version: string
  config_json: Record<string, unknown>
  english_summary: string | null
  status: string // DRAFT | PENDING_APPROVAL | APPROVED | SUPERSEDED
  author_id: string | null
  approver_id: string | null
  parent_id: number | null
  superseded_by: number | null
  origin: string
  created_at: string
  approved_at: string | null
  repairs_applied: string[]
}

export interface RunOut {
  id: number
  config_id: number
  config_version: string
  matched_count: number
  break_count: number
  total_a: number
  total_b: number
  match_rate: number // percentage 0..100
  position_proof_status: string | null
  regulatory_escalation_count: number
  duration_ms: number | null
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

export interface FailedRule {
  field_a: string
  field_b: string
  match_type: string
  value_a: unknown
  value_b: unknown
  delta: number | null
}

export interface RootCauseTree {
  data_layer: { summary: string; isin: string | null; side: string | null }
  rule_that_failed: { pass: number | null; field: string; deltas: Record<string, unknown> }
  ai_diagnosis: { primary_hypothesis: string; evidence: string[]; alternative: string }
}

export interface BreakOut {
  id: number
  run_id: number
  break_key: string
  side: string | null
  row_a: Record<string, unknown> | null
  row_b: Record<string, unknown> | null
  failed_rules: FailedRule[]
  deltas: Record<string, unknown>
  isin: string | null
  currency: string | null
  asset_class: string | null
  pass_that_failed: number | null
  archetype: string | null
  causal_origin: string | null
  field_most_responsible: string | null
  root_cause_tree: RootCauseTree | null
  explanation: string | null
  regulatory_narrative: string | null
  suggested_resolution: string | null
  sme_confidence: number | null
  judge_confidence: number | null
  judge_decision: string | null
  autonomy_route: string | null
  regulatory_escalation_required: boolean
  age_business_days: number
  severity: string
  status: string
  created_at: string
}

export interface PositionProofOut {
  side: string
  status: string
  opening: number
  computed_closing: number
  stated_closing: number
  variance: number
  unexplained_variance: number
}

export interface PassStatOut {
  pass_number: number | null
  pass_name: string | null
  match_type: string | null
  matched_count: number
  pool_a_remaining: number
  pool_b_remaining: number
}

export interface RunSummaryOut {
  run: RunOut
  position_proof_status: string | null
  archetype_counts: Record<string, number>
  status_counts: Record<string, number>
  regulatory_escalation_count: number
}

export interface BreakAnalysisOut {
  break_id: number
  archetype: string
  causal_origin: string
  field_most_responsible: string
  confidence: number
  autonomy_route: string
  refuse_to_classify: boolean
  routing_rationale: string
}

// Governance
export interface GovernanceActionOut {
  id: number
  break_id: number
  action_type: string
  maker_id: string
  checker_id: string | null
  status: string
  maker_notes: string | null
  checker_notes: string | null
  rejection_reason: string | null
  submitted_at: string
  decided_at: string | null
  expires_at: string | null
}

export interface PendingActionOut extends GovernanceActionOut {
  time_remaining_seconds: number
}

export interface JournalEntryOut {
  id: number
  entry_type: string
  debit_account: string
  credit_account: string
  amount: number
  currency: string
  isin: string | null
  narrative: string
  approved_by: string
  audit_reference: string
}

export interface MakerSubmitOut {
  action: GovernanceActionOut
  journal_entry: JournalEntryOut | null
}

export interface CheckerDecisionOut {
  status: string
  journal_entry: JournalEntryOut | null
}

// Regulatory
export interface RegulatoryNotificationOut {
  id: number
  break_id: number
  regime: string
  competent_authority: string
  notification_draft: string
  dispute_amount: number | null
  dispute_days: number | null
  status: string
  approved_by: string | null
  created_at: string
}

export interface CassReconciliationOut {
  id: number
  reconciliation_date: string
  client_liability_total: number
  safeguarded_funds_total: number
  shortfall_amount: number | null
  shortfall_status: string
  resolution_pack_hash: string | null
  created_at: string
}

// Loops
export interface LoopAProposeOutV2 {
  new_config: ConfigOut
  rationale: string
  cap_note: string | null
}

export interface LoopAAggregateOut {
  pattern: { pattern: string; delta: number; count: number } | null
  manual_match_count: number
}

export interface LoopAWhatIfOut {
  current_match_rate: number
  candidate_match_rate: number
  current_matched: number
  candidate_matched: number
  newly_matched_keys: string[]
  newly_broken_keys: string[]
}

export interface ResolutionMemoryOut {
  id: number
  feature_key: string
  archetype: string
  causal_origin: string | null
  resolution: string
  confidence: number
  times_seen: number
  usage_count: number
}

// Client portal
export interface ClientUploadOut {
  run_id: number
  match_rate: number
  matched_count: number
  break_count: number
  output_hash: string
}

export interface ClientBreakOut {
  break_id: number
  isin: string | null
  issue: string
  status: string
  amount: number | null
}

export interface ClientReconOut {
  run_id: number
  match_rate: number
  matched_count: number
  break_count: number
  breaks: ClientBreakOut[]
}

export interface EvidencePack {
  run_id: number
  recon_name: string
  match_rate: number
  output_hash: string
  position_proof_status: string | null
  break_count: number
  generated_at: string
  document_hash: string
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

export const ARCHETYPE_LABELS: Record<string, string> = {
  settlement_date_drift: 'Settlement date drift',
  quantity_rounding: 'Quantity rounding',
  fx_price_rounding: 'FX / price rounding',
  one_to_many_split: 'One-to-many split',
  many_to_one_aggregate: 'Many-to-one aggregate',
  nm_subset_group: 'N-to-M subset group',
  missing_leg: 'Missing counterparty leg',
  duplicate_entry: 'Duplicate entry',
  account_misbooking: 'Account misbooking',
  emir_amount_dispute: 'EMIR market-value dispute',
  corporate_action_adjustment: 'Corporate action adjustment',
  cass_shortfall: 'CASS safeguarding shortfall',
}

export const ROUTE_LABELS: Record<string, string> = {
  STP_AUTO_RESOLVE: 'Auto-resolved (STP)',
  MAKER_REVIEW_REQUIRED: 'Maker review',
  ESCALATE_SENIOR: 'Escalate to senior',
  REGULATORY_ESCALATION: 'Regulatory escalation',
}
