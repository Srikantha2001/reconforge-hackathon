import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, CardContent, Divider, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, Typography,
} from '@mui/material'
import { useAuth } from '../context/AuthContext'
import { api, ApiError } from '../api'
import type { ConfigOut, LoopAAggregateOut, LoopAProposeOutV2, LoopAWhatIfOut, ResolutionMemoryOut, RunOut } from '../types'
import { ARCHETYPE_LABELS } from '../types'
import { Figure } from '../components/Figure'
import { VersionChip } from '../components/VersionChip'

interface Props {
  run: RunOut | null
  onNewConfig: (c: ConfigOut) => void
}

export function LearningPage({ run, onNewConfig }: Props) {
  const { role } = useAuth()
  const [agg, setAgg] = useState<LoopAAggregateOut | null>(null)
  const [proposal, setProposal] = useState<LoopAProposeOutV2 | null>(null)
  const [whatIf, setWhatIf] = useState<LoopAWhatIfOut | null>(null)
  const [memory, setMemory] = useState<ResolutionMemoryOut[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = () => {
    if (run) api.loopAAggregate(run.id).then(setAgg).catch(() => {})
    api.resolutionMemory().then(setMemory).catch(() => {})
  }
  useEffect(reload, [run])

  const isMaker = role === 'MAKER' || role === 'ADMIN'
  const isChecker = role === 'CHECKER' || role === 'ADMIN'

  const propose = async () => {
    if (!run) return
    setBusy('propose'); setError(null); setWhatIf(null)
    try {
      const p = await api.loopAPropose(run.id)
      setProposal(p)
      setWhatIf(await api.loopAWhatIf(run.id, p.new_config.id))
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Propose failed')
    } finally { setBusy(null) }
  }

  const approve = async () => {
    if (!proposal) return
    setBusy('approve'); setError(null)
    try {
      const cfg = await api.approveConfig(proposal.new_config.id, true)
      onNewConfig(cfg)
      setProposal(null); setWhatIf(null); reload()
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Approve failed')
    } finally { setBusy(null) }
  }

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Loop A — config refinement</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Force-matched breaks are aggregated by which rule disagreed; a systemic pattern proposes
            widening that rule — through the same maker-checker gate. DATE_TOLERANCE is capped at 5 days.
          </Typography>

          {!run && <Alert severity="info">Run a reconciliation first.</Alert>}
          {run && agg && (
            <Alert severity={agg.pattern ? 'success' : 'info'} variant="outlined" sx={{ mb: 2 }}>
              {agg.pattern
                ? `Pattern detected: ${agg.pattern.count}× ${agg.pattern.pattern} (delta ${agg.pattern.delta}). ${agg.manual_match_count} force-matches recorded.`
                : `No systemic pattern yet — ${agg.manual_match_count} force-match(es) recorded (need 4+ of the same drift).`}
            </Alert>
          )}

          {isMaker && run && agg?.pattern && !proposal && (
            <Button variant="contained" onClick={propose} disabled={Boolean(busy)}>
              {busy === 'propose' ? 'Proposing…' : 'Propose config change'}
            </Button>
          )}
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        </CardContent>
      </Card>

      {proposal && (
        <Card>
          <CardContent>
            <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="h6">Proposed change</Typography>
              <VersionChip version={proposal.new_config.version} status={proposal.new_config.status} />
            </Stack>
            <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>{proposal.rationale}</Alert>
            {proposal.cap_note && <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>{proposal.cap_note}</Alert>}

            {whatIf && (
              <>
                <Divider sx={{ my: 1 }} />
                <Stack direction="row" spacing={4} sx={{ my: 1 }}>
                  <Metric label="Current match rate" value={`${whatIf.current_match_rate.toFixed(1)}%`} />
                  <Metric label="Candidate match rate" value={`${whatIf.candidate_match_rate.toFixed(1)}%`} accent="#2E7D46" />
                </Stack>
                <Typography variant="body2" color="success.main">
                  Auto-matches <Figure>{whatIf.newly_matched_keys.length}</Figure>, risks{' '}
                  <Figure>{whatIf.newly_broken_keys.length}</Figure>
                </Typography>
                {whatIf.newly_broken_keys.length > 0 && (
                  <Alert severity="warning" variant="outlined" sx={{ mt: 1 }}>
                    Newly broken (never hidden): {whatIf.newly_broken_keys.join(', ')}
                  </Alert>
                )}
              </>
            )}

            {isChecker && (
              <Button variant="contained" color="success" sx={{ mt: 2 }} onClick={approve} disabled={busy === 'approve'}>
                {busy === 'approve' ? 'Approving…' : 'Approve & supersede'}
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {memory.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Loop B — resolution memory</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Archetype</TableCell>
                  <TableCell>Resolution</TableCell>
                  <TableCell>Confidence</TableCell>
                  <TableCell>Seen</TableCell>
                  <TableCell>Used</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {memory.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{ARCHETYPE_LABELS[m.archetype] ?? m.archetype}</TableCell>
                    <TableCell sx={{ maxWidth: 340 }}>{m.resolution}</TableCell>
                    <TableCell><Figure>{(m.confidence * 100).toFixed(0)}%</Figure></TableCell>
                    <TableCell><Figure>{m.times_seen}</Figure></TableCell>
                    <TableCell><Figure>{m.usage_count}</Figure></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </Stack>
  )
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <Stack>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h5" sx={{ color: accent ?? 'text.primary' }}><Figure>{value}</Figure></Typography>
    </Stack>
  )
}
