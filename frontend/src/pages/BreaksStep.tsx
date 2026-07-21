import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { useActor } from '../context/ActorContext'
import { api, ApiError } from '../api'
import type { AdviseOut, BreakOut, ChaserOut, DashboardOut, RunOut } from '../types'
import { ARCHETYPE_LABELS } from '../types'
import { SeverityChip } from '../components/SeverityChip'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { Figure } from '../components/Figure'

function RowDiff({ row_a, row_b }: { row_a: Record<string, unknown> | null; row_b: Record<string, unknown> | null }) {
  const keys = Array.from(new Set([...(row_a ? Object.keys(row_a) : []), ...(row_b ? Object.keys(row_b) : [])]))
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Field</TableCell>
          <TableCell>Row A (ledger)</TableCell>
          <TableCell>Row B (statement)</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {keys.map((k) => {
          const va = row_a?.[k]
          const vb = row_b?.[k]
          const differs = row_a && row_b && String(va) !== String(vb)
          return (
            <TableRow key={k}>
              <TableCell>{k}</TableCell>
              <TableCell sx={{ bgcolor: differs ? 'warning.main' : undefined, opacity: differs ? 0.9 : 1 }}>
                <Figure>{va === undefined ? '—' : String(va)}</Figure>
              </TableCell>
              <TableCell sx={{ bgcolor: differs ? 'warning.main' : undefined, opacity: differs ? 0.9 : 1 }}>
                <Figure>{vb === undefined ? '—' : String(vb)}</Figure>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

interface BreakDrilldownProps {
  brk: BreakOut
  onClose: () => void
  onUpdated: (b: BreakOut) => void
}

function BreakDrilldown({ brk, onClose, onUpdated }: BreakDrilldownProps) {
  const { actingAs } = useActor()
  const [advice, setAdvice] = useState<AdviseOut | null>(null)
  const [chaser, setChaser] = useState<ChaserOut | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resolution, setResolution] = useState(brk.suggested_resolution ?? '')

  const advise = async () => {
    setLoading('advise')
    setError(null)
    try {
      const result = await api.adviseBreak(brk.id, actingAs)
      setAdvice(result)
      setResolution(result.suggested_resolution)
      const fresh = await api.getBreak(brk.id)
      onUpdated(fresh)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Advise failed')
    } finally {
      setLoading(null)
    }
  }

  const draftChaser = async () => {
    setLoading('chaser')
    setError(null)
    try {
      setChaser(await api.chaserDraft(brk.id, actingAs))
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Chaser draft failed')
    } finally {
      setLoading(null)
    }
  }

  const manualMatch = async () => {
    setLoading('match')
    setError(null)
    try {
      const fresh = await api.manualMatch(brk.id, actingAs)
      onUpdated(fresh)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Manual match failed — one-sided breaks need a counterpart row')
    } finally {
      setLoading(null)
    }
  }

  const resolve = async () => {
    setLoading('resolve')
    setError(null)
    try {
      const fresh = await api.resolveBreak(brk.id, {
        actor_id: actingAs,
        confirmed_archetype: brk.archetype ?? 'amount_outside_tolerance',
        confirmed_resolution: resolution,
      })
      onUpdated(fresh)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Resolve failed')
    } finally {
      setLoading(null)
    }
  }

  const canManualMatch = Boolean(brk.row_a && brk.row_b)

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box>
          <Figure sx={{ fontWeight: 600 }}>{brk.break_key}</Figure>{' '}
          <Chip size="small" sx={{ ml: 1 }} label={ARCHETYPE_LABELS[brk.archetype ?? ''] ?? brk.archetype} />
          <SeverityChip severity={brk.severity} />
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <RowDiff row_a={brk.row_a} row_b={brk.row_b} />

          <Alert severity="info" variant="outlined">
            {brk.explanation}
          </Alert>

          {brk.suggested_resolution && (
            <Typography variant="body2" color="text.secondary">
              Suggested: {brk.suggested_resolution}
            </Typography>
          )}

          {(brk.sme_confidence !== null || brk.judge_decision) && (
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
              {brk.sme_confidence !== null && (
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Typography variant="caption" color="text.secondary">
                    SME confidence
                  </Typography>
                  <ConfidenceBadge confidence={brk.sme_confidence} />
                </Stack>
              )}
              {brk.judge_decision && (
                <Chip
                  size="small"
                  label={brk.judge_decision === 'accept' ? 'Auto-accepted' : 'Routed to human'}
                  color={brk.judge_decision === 'accept' ? 'success' : 'warning'}
                />
              )}
            </Stack>
          )}

          {advice && advice.source === 'resolution_memory' && (
            <Alert severity="success" variant="outlined">
              Short-circuited via resolution memory — this pattern has been seen before.
            </Alert>
          )}

          {chaser && (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="caption" color="text.secondary">
                  Chaser draft — never sent automatically, review before sending
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  <strong>To:</strong> {chaser.to}
                </Typography>
                <Typography variant="body2">
                  <strong>Subject:</strong> {chaser.subject}
                </Typography>
                <Typography variant="body2" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                  {chaser.body}
                </Typography>
              </CardContent>
            </Card>
          )}

          <Divider />

          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              Confirm resolution (feeds resolution memory — Loop B)
            </Typography>
            <TextField
              multiline
              minRows={2}
              size="small"
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
            />
          </Stack>

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, flexWrap: 'wrap', gap: 1 }}>
        <Button onClick={advise} disabled={Boolean(loading)} variant="outlined">
          {loading === 'advise' ? 'Advising…' : 'Advise (SME + Judge)'}
        </Button>
        <Button onClick={draftChaser} disabled={Boolean(loading)} variant="outlined">
          {loading === 'chaser' ? 'Drafting…' : 'Draft chaser'}
        </Button>
        <Button onClick={manualMatch} disabled={Boolean(loading) || !canManualMatch} variant="outlined">
          {loading === 'match' ? 'Matching…' : 'Manual match (Loop A)'}
        </Button>
        <Button onClick={resolve} disabled={Boolean(loading)} variant="contained">
          {loading === 'resolve' ? 'Resolving…' : 'Resolve (Loop B)'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

interface BreaksStepProps {
  run: RunOut
}

export function BreaksStep({ run }: BreaksStepProps) {
  const [breaks, setBreaks] = useState<BreakOut[]>([])
  const [dashboard, setDashboard] = useState<DashboardOut | null>(null)
  const [selected, setSelected] = useState<BreakOut | null>(null)

  const reload = () => {
    api.runBreaks(run.id).then(setBreaks)
    api.runDashboard(run.id).then(setDashboard)
  }

  useEffect(reload, [run.id])

  const updateBreak = (b: BreakOut) => {
    setBreaks((prev) => prev.map((x) => (x.id === b.id ? b : x)))
    setSelected(b)
    api.runDashboard(run.id).then(setDashboard)
  }

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            4. Breaks board
          </Typography>
          {dashboard && (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: 1 }}>
              {Object.entries(dashboard.archetype_counts).map(([k, v]) => (
                <Chip key={k} size="small" variant="outlined" label={`${ARCHETYPE_LABELS[k] ?? k}: ${v}`} />
              ))}
            </Stack>
          )}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Key</TableCell>
                <TableCell>Archetype</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Confidence</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {breaks.map((b) => (
                <TableRow key={b.id} hover>
                  <TableCell>
                    <Figure>{b.break_key}</Figure>
                  </TableCell>
                  <TableCell>{ARCHETYPE_LABELS[b.archetype ?? ''] ?? b.archetype}</TableCell>
                  <TableCell>
                    <SeverityChip severity={b.severity} />
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={b.status} variant="outlined" />
                  </TableCell>
                  <TableCell>{b.sme_confidence !== null && <ConfidenceBadge confidence={b.sme_confidence} />}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setSelected(b)}>
                      Inspect
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <BreakDrilldown brk={selected} onClose={() => setSelected(null)} onUpdated={updateBreak} />
      )}
    </Stack>
  )
}
