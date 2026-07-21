import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { useActor } from '../context/ActorContext'
import { api, ApiError } from '../api'
import type { BreakOut, ConfigOut, DashboardOut, RunOut } from '../types'
import { ARCHETYPE_LABELS } from '../types'
import { SplitMatchedBar } from '../components/SplitMatchedBar'
import { Figure } from '../components/Figure'
import { SeverityChip } from '../components/SeverityChip'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { BreakDrilldown } from '../components/BreakDrilldown'

interface RunStepProps {
  config: ConfigOut
  run: RunOut | null
  useSeed: boolean
  sourceFile: File | null
  targetFile: File | null
  onRunCreated: (run: RunOut) => void
}

export function RunStep({ config, run, useSeed, sourceFile, targetFile, onRunCreated }: RunStepProps) {
  const { actingAs } = useActor()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [repro, setRepro] = useState<{ reproducible: boolean; recomputed_hash: string } | null>(null)

  const [breaks, setBreaks] = useState<BreakOut[]>([])
  const [dashboard, setDashboard] = useState<DashboardOut | null>(null)
  const [selected, setSelected] = useState<BreakOut | null>(null)

  useEffect(() => {
    if (run) {
      api.runBreaks(run.id).then(setBreaks)
      api.runDashboard(run.id).then(setDashboard)
    }
  }, [run?.id])

  const runRecon = async () => {
    setLoading(true)
    setError(null)
    setRepro(null)
    try {
      const result = useSeed
        ? await api.createRunFromSeed(config.id, actingAs)
        : sourceFile && targetFile
          ? await api.createRunFromUpload(config.id, actingAs, sourceFile, targetFile)
          : null
      if (!result) {
        setError('Choose both a source and target CSV back in Configure, or use the seeded pair.')
        return
      }
      onRunCreated(result)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Run failed')
    } finally {
      setLoading(false)
    }
  }

  const checkRepro = async () => {
    if (!run) return
    const result = await api.reproducibilityCheck(run.id)
    setRepro(result)
  }

  const updateBreak = (b: BreakOut) => {
    setBreaks((prev) => prev.map((x) => (x.id === b.id ? b : x)))
    setSelected(b)
    if (run) api.runDashboard(run.id).then(setDashboard)
  }

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            2. Run — {config.recon_name}{' '}
            <Typography component="span" color="text.secondary" variant="body2">
              (v{config.version})
            </Typography>
          </Typography>

          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <Button variant="contained" onClick={runRecon} disabled={loading}>
              {loading ? 'Running…' : 'Run reconciliation'}
            </Button>
            <Typography variant="caption" color="text.secondary">
              {useSeed
                ? 'Using rehearsed seeded pair (ledger.csv / statement.csv)'
                : sourceFile && targetFile
                  ? `${sourceFile.name} + ${targetFile.name}`
                  : 'No files selected — go back to Configure to upload'}
            </Typography>
          </Stack>

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>

      {run && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Result
            </Typography>
            <SplitMatchedBar matched={run.matched_count} breaks={run.break_count} />

            <Stack direction="row" spacing={4} sx={{ mt: 3 }}>
              <Stack>
                <Typography variant="caption" color="text.secondary">
                  Match rate
                </Typography>
                <Typography variant="h4">
                  <Figure>{(run.match_rate * 100).toFixed(1)}%</Figure>
                </Typography>
              </Stack>
              <Stack>
                <Typography variant="caption" color="text.secondary">
                  Rows
                </Typography>
                <Typography variant="h4">
                  <Figure>
                    {run.total_a} / {run.total_b}
                  </Figure>
                </Typography>
              </Stack>
            </Stack>

            <Divider sx={{ my: 2 }} />

            <Typography variant="caption" color="text.secondary">
              Output hash (same input → identical hash, every run)
            </Typography>
            <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
              <Figure>{run.output_hash}</Figure>
            </Typography>

            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mt: 2 }}>
              <Button variant="outlined" size="small" onClick={checkRepro}>
                Verify reproducibility
              </Button>
              {repro && (
                <Alert severity={repro.reproducible ? 'success' : 'error'} sx={{ py: 0 }}>
                  {repro.reproducible
                    ? 'Reproducible — a control, not a guess.'
                    : 'Hash mismatch — investigate immediately.'}
                </Alert>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      {run && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Breaks board
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
      )}

      {selected && (
        <BreakDrilldown brk={selected} onClose={() => setSelected(null)} onUpdated={updateBreak} />
      )}
    </Stack>
  )
}
