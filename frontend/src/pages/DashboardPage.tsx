import { useEffect, useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, Typography,
} from '@mui/material'
import { useAuth } from '../context/AuthContext'
import { api, ApiError } from '../api'
import type { ConfigOut, PassStatOut, PositionProofOut, RunOut } from '../types'
import { Figure } from '../components/Figure'
import { PositionProofCard } from '../components/PositionProofCard'
import { WaterfallChart } from '../components/WaterfallChart'
import { SeverityChip } from '../components/SeverityChip'
import { ARCHETYPE_LABELS } from '../types'

interface Props {
  config: ConfigOut | null
  run: RunOut | null
  onRun: (r: RunOut) => void
  onGoConfigure: () => void
}

export function DashboardPage({ config, run, onRun, onGoConfigure }: Props) {
  const { role } = useAuth()
  const [approved, setApproved] = useState<ConfigOut | null>(config)
  const [proof, setProof] = useState<PositionProofOut | null>(null)
  const [passes, setPasses] = useState<PassStatOut[]>([])
  const [topBreaks, setTopBreaks] = useState<{ id: number; break_key: string; archetype: string | null; severity: string; isin: string | null }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!approved) {
      api.listConfigs().then((cs) => setApproved(cs.find((c) => c.status === 'APPROVED') ?? null)).catch(() => {})
    }
  }, [approved])

  useEffect(() => {
    if (!run) return
    api.positionProof(run.id).then((pp) => setProof(pp.find((p) => p.side === 'A') ?? null)).catch(() => {})
    api.waterfall(run.id).then(setPasses).catch(() => {})
    api.breaksByRun(run.id).then((bs) =>
      setTopBreaks(bs.slice(0, 5).map((b) => ({ id: b.id, break_key: b.break_key, archetype: b.archetype, severity: b.severity, isin: b.isin })))
    ).catch(() => {})
  }, [run])

  const execute = async () => {
    if (!approved) return
    setLoading(true)
    setError(null)
    try {
      onRun(await api.createRunFromSeed(approved.id))
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Run failed')
    } finally {
      setLoading(false)
    }
  }

  const canRun = (role === 'MAKER' || role === 'ADMIN') && approved

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="h6">Run reconciliation</Typography>
              <Typography variant="body2" color="text.secondary">
                {approved ? `${approved.recon_name} v${approved.version} (APPROVED)` : 'No approved config yet'}
              </Typography>
            </Box>
            {approved ? (
              canRun && (
                <Button variant="contained" onClick={execute} disabled={loading}>
                  {loading ? 'Running…' : 'Execute on seed'}
                </Button>
              )
            ) : (
              <Button variant="outlined" onClick={onGoConfigure}>Go to Configure</Button>
            )}
          </Stack>
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        </CardContent>
      </Card>

      {run && (
        <>
          <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', gap: 2 }}>
            <Kpi label="Rows (A / B)" value={`${run.total_a} / ${run.total_b}`} />
            <Kpi label="Match rate" value={`${run.match_rate.toFixed(1)}%`} accent="#2E7D46" />
            <Kpi label="Matched" value={run.matched_count} accent="#2E7D46" />
            <Kpi label="Breaks" value={run.break_count} accent="#B4790A" />
            <Kpi label="Regulatory" value={run.regulatory_escalation_count} accent="#B3261E" />
          </Stack>

          <PositionProofCard run={run} proof={proof} />
          {passes.length > 0 && <WaterfallChart passes={passes} />}

          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Top breaks</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Key</TableCell>
                    <TableCell>ISIN</TableCell>
                    <TableCell>Archetype</TableCell>
                    <TableCell>Severity</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topBreaks.map((b) => (
                    <TableRow key={b.id} hover>
                      <TableCell><Figure>{b.break_key}</Figure></TableCell>
                      <TableCell><Figure>{b.isin}</Figure></TableCell>
                      <TableCell>{ARCHETYPE_LABELS[b.archetype ?? ''] ?? b.archetype ?? '—'}</TableCell>
                      <TableCell><SeverityChip severity={b.severity} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </Stack>
  )
}

function Kpi({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <Card sx={{ flex: '1 1 150px', minWidth: 140 }}>
      <CardContent>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h4" sx={{ color: accent ?? 'text.primary' }}>
          <Figure>{value}</Figure>
        </Typography>
      </CardContent>
    </Card>
  )
}
