import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, MenuItem, Select, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { useAuth } from '../context/AuthContext'
import { api, ApiError } from '../api'
import type { BreakOut, RunOut } from '../types'
import { ARCHETYPE_LABELS, ROUTE_LABELS } from '../types'
import { Figure } from '../components/Figure'
import { SeverityChip } from '../components/SeverityChip'
import { StatusChip } from '../components/StatusChip'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { RootCauseTree } from '../components/RootCauseTree'

const GOV_ACTIONS = ['FORCE_MATCH', 'WRITE_OFF', 'INVESTIGATE', 'AWAIT_COUNTERPARTY']

export function BreaksPage({ run }: { run: RunOut | null }) {
  const { role } = useAuth()
  const [breaks, setBreaks] = useState<BreakOut[]>([])
  const [status, setStatus] = useState('')
  const [archetype, setArchetype] = useState('')
  const [regOnly, setRegOnly] = useState(false)
  const [isin, setIsin] = useState('')
  const [selected, setSelected] = useState<BreakOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!run) return
    const bs = await api.breaksByRun(run.id, { status: status || undefined, archetype: archetype || undefined, regulatory_only: regOnly })
    setBreaks(isin ? bs.filter((b) => (b.isin ?? '').toLowerCase().includes(isin.toLowerCase())) : bs)
  }, [run, status, archetype, regOnly, isin])

  useEffect(() => { reload().catch(() => {}) }, [reload])

  const analyze = async () => {
    if (!run) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await api.analyzeBreaks(run.id)
      setMsg(`Analyzed ${res.length} breaks — SME classified, Judge routed.`)
      await reload()
    } catch (e) {
      setMsg(e instanceof ApiError ? String(e.message) : 'Analyze failed')
    } finally {
      setBusy(false)
    }
  }

  if (!run) return <Alert severity="info">Run a reconciliation from the Dashboard first.</Alert>

  const isMaker = role === 'MAKER' || role === 'ADMIN'
  const archetypes = Array.from(new Set(breaks.map((b) => b.archetype).filter(Boolean))) as string[]

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">Breaks board — run #{run.id}</Typography>
            {isMaker && (
              <Button variant="contained" onClick={analyze} disabled={busy}>
                {busy ? 'Analyzing…' : 'Analyze breaks (SME + Judge)'}
              </Button>
            )}
          </Stack>
          {msg && <Alert severity="info" sx={{ mb: 2 }}>{msg}</Alert>}

          <Stack direction="row" spacing={1.5} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
            <Select size="small" displayEmpty value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 140 }}>
              <MenuItem value="">All statuses</MenuItem>
              <MenuItem value="open">Open</MenuItem>
              <MenuItem value="RESOLVED_STP">Resolved (STP)</MenuItem>
              <MenuItem value="RESOLVED_APPROVED">Resolved (approved)</MenuItem>
              <MenuItem value="PENDING_REGULATORY_ACTION">Regulatory</MenuItem>
              <MenuItem value="explained">Explained</MenuItem>
            </Select>
            <Select size="small" displayEmpty value={archetype} onChange={(e) => setArchetype(e.target.value)} sx={{ minWidth: 160 }}>
              <MenuItem value="">All archetypes</MenuItem>
              {archetypes.map((a) => <MenuItem key={a} value={a}>{ARCHETYPE_LABELS[a] ?? a}</MenuItem>)}
            </Select>
            <TextField size="small" placeholder="ISIN" value={isin} onChange={(e) => setIsin(e.target.value)} />
            <Chip
              label="Regulatory only"
              color={regOnly ? 'error' : 'default'}
              variant={regOnly ? 'filled' : 'outlined'}
              onClick={() => setRegOnly((v) => !v)}
            />
          </Stack>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Key</TableCell>
                <TableCell>ISIN</TableCell>
                <TableCell>Archetype</TableCell>
                <TableCell>Confidence</TableCell>
                <TableCell>Route</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Status</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {breaks.map((b) => (
                <TableRow key={b.id} hover>
                  <TableCell><Figure>{b.break_key}</Figure></TableCell>
                  <TableCell><Figure>{b.isin}</Figure></TableCell>
                  <TableCell>{ARCHETYPE_LABELS[b.archetype ?? ''] ?? b.archetype ?? '—'}</TableCell>
                  <TableCell>{b.sme_confidence != null && <ConfidenceBadge confidence={b.sme_confidence} />}</TableCell>
                  <TableCell>
                    {b.autonomy_route && <Chip size="small" variant="outlined" label={ROUTE_LABELS[b.autonomy_route] ?? b.autonomy_route} />}
                  </TableCell>
                  <TableCell><SeverityChip severity={b.severity} /></TableCell>
                  <TableCell><StatusChip status={b.status} /></TableCell>
                  <TableCell align="right"><Button size="small" onClick={() => setSelected(b)}>Inspect</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <BreakDialog
          brk={selected}
          canAct={isMaker}
          onClose={() => setSelected(null)}
          onActed={async () => { setSelected(null); await reload() }}
        />
      )}
    </Stack>
  )
}

function BreakDialog({ brk, canAct, onClose, onActed }: {
  brk: BreakOut; canAct: boolean; onClose: () => void; onActed: () => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (action: string) => {
    setBusy(action)
    setError(null)
    try {
      await api.makerSubmit(brk.id, action)
      onActed()
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Submit failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box>
          <Figure sx={{ fontWeight: 700 }}>{brk.break_key}</Figure>
          <Chip size="small" sx={{ ml: 1 }} label={ARCHETYPE_LABELS[brk.archetype ?? ''] ?? brk.archetype} />
          <SeverityChip severity={brk.severity} />
        </Box>
        <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {brk.root_cause_tree
            ? <RootCauseTree tree={brk.root_cause_tree} />
            : <Alert severity="info">Not analyzed yet — run "Analyze breaks" to populate the root-cause tree.</Alert>}

          {brk.regulatory_narrative && (
            <Alert severity="error" variant="outlined">
              <Typography variant="caption" sx={{ fontWeight: 700 }}>Regulatory narrative</Typography>
              <Typography variant="body2">{brk.regulatory_narrative}</Typography>
            </Alert>
          )}

          {brk.suggested_resolution && (
            <Box>
              <Typography variant="caption" color="text.secondary">Suggested resolution</Typography>
              <Typography variant="body2">{brk.suggested_resolution}</Typography>
            </Box>
          )}

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      {canAct && brk.status === 'open' && (
        <DialogActions sx={{ px: 3, py: 2, flexWrap: 'wrap', gap: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mr: 'auto' }}>
            Submit a governance action (a checker approves it):
          </Typography>
          {GOV_ACTIONS.map((a) => (
            <Button key={a} size="small" variant="outlined" disabled={Boolean(busy)} onClick={() => submit(a)}>
              {busy === a ? '…' : a.replaceAll('_', ' ').toLowerCase()}
            </Button>
          ))}
        </DialogActions>
      )}
    </Dialog>
  )
}
