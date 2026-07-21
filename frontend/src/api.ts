// Thin fetch wrapper for the ReconForge API. Relative '/api' path is proxied
// to the backend by Vite in dev (see vite.config.ts); in production, serve
// behind a reverse proxy that forwards /api the same way.
import type {
  Actor,
  AdviseOut,
  AuditLogOut,
  BreakOut,
  ChaserOut,
  ConfigOut,
  DashboardOut,
  LoopAAggregateGroup,
  LoopAProposeOut,
  LoopAWhatIfOut,
  ReproducibilityCheckOut,
  ResolutionMemoryOut,
  RunOut,
  SeedInfo,
} from './types'

const BASE = '/api'

class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail: unknown
    try {
      detail = await resp.json()
    } catch {
      detail = await resp.text()
    }
    throw new ApiError(resp.status, (detail as { detail?: unknown })?.detail ?? detail)
  }
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined })

export const api = {
  health: () => get<{ status: string; llm_provider: string }>('/health'),
  actors: () => get<Actor[]>('/actors'),

  seedInfo: () => get<SeedInfo>('/seed/info'),
  seedGenerate: () => post<{ status: string; dir: string }>('/seed/generate'),

  authorConfig: (body: {
    nl_description: string
    actor_id: string
    columns_a: string[]
    columns_b: string[]
    recon_name_hint?: string
  }) => post<ConfigOut>('/configs/author', body),
  getConfig: (id: number) => get<ConfigOut>(`/configs/${id}`),
  listConfigs: (recon_name?: string) =>
    get<ConfigOut[]>(`/configs${recon_name ? `?recon_name=${encodeURIComponent(recon_name)}` : ''}`),
  editConfig: (id: number, body: { config_json: unknown; actor_id: string }) =>
    post<ConfigOut>(`/configs/${id}/edit`, body),
  approveConfig: (id: number, actor_id: string) => post<ConfigOut>(`/configs/${id}/approve`, { actor_id }),

  createRunFromSeed: (config_id: number, actor_id: string) => {
    const form = new FormData()
    form.append('config_id', String(config_id))
    form.append('actor_id', actor_id)
    form.append('use_seed', 'true')
    return request<RunOut>('/runs', { method: 'POST', body: form })
  },
  createRunFromUpload: (config_id: number, actor_id: string, ledger: File, statement: File) => {
    const form = new FormData()
    form.append('config_id', String(config_id))
    form.append('actor_id', actor_id)
    form.append('use_seed', 'false')
    form.append('ledger_file', ledger)
    form.append('statement_file', statement)
    return request<RunOut>('/runs', { method: 'POST', body: form })
  },
  getRun: (id: number) => get<RunOut>(`/runs/${id}`),
  listRuns: (config_id?: number) => get<RunOut[]>(`/runs${config_id ? `?config_id=${config_id}` : ''}`),
  reproducibilityCheck: (runId: number) =>
    post<ReproducibilityCheckOut>(`/runs/${runId}/reproducibility-check`),
  runBreaks: (runId: number) => get<BreakOut[]>(`/runs/${runId}/breaks`),
  runDashboard: (runId: number) => get<DashboardOut>(`/runs/${runId}/dashboard`),

  getBreak: (id: number) => get<BreakOut>(`/breaks/${id}`),
  adviseBreak: (id: number, actor_id: string) => post<AdviseOut>(`/breaks/${id}/advise`, { actor_id }),
  chaserDraft: (id: number, actor_id: string) => post<ChaserOut>(`/breaks/${id}/chaser`, { actor_id }),
  manualMatch: (id: number, actor_id: string) => post<BreakOut>(`/breaks/${id}/manual-match`, { actor_id }),
  resolveBreak: (
    id: number,
    body: { actor_id: string; confirmed_archetype: string; confirmed_resolution: string },
  ) => post<BreakOut>(`/breaks/${id}/resolve`, body),

  loopAAggregate: (runId: number) => get<LoopAAggregateGroup[]>(`/runs/${runId}/loop-a/aggregate`),
  loopAPropose: (
    runId: number,
    body: { actor_id: string; field_a: string; field_b: string; type: string },
  ) => post<LoopAProposeOut>(`/runs/${runId}/loop-a/propose`, body),
  loopAWhatIf: (runId: number, candidate_config_id: number) =>
    post<LoopAWhatIfOut>(`/runs/${runId}/loop-a/what-if`, { candidate_config_id }),

  resolutionMemory: () => get<ResolutionMemoryOut[]>('/resolution-memory'),

  auditLog: (params?: { entity_type?: string; entity_id?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.entity_type) q.set('entity_type', params.entity_type)
    if (params?.entity_id) q.set('entity_id', params.entity_id)
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<AuditLogOut[]>(`/audit${qs ? `?${qs}` : ''}`)
  },
}

export { ApiError }
