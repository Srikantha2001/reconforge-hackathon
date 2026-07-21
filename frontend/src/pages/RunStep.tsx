import { useState } from 'react'
import {
  Alert,
  Button,
  Card,
  CardContent,
  Divider,
  FormControlLabel,
  Stack,
  Switch,
  Typography,
} from '@mui/material'
import { useActor } from '../context/ActorContext'
import { api, ApiError } from '../api'
import type { ConfigOut, RunOut } from '../types'
import { SplitMatchedBar } from '../components/SplitMatchedBar'
import { Figure } from '../components/Figure'

interface RunStepProps {
  config: ConfigOut
  run: RunOut | null
  onRunCreated: (run: RunOut) => void
}

export function RunStep({ config, run, onRunCreated }: RunStepProps) {
  const { actingAs } = useActor()
  const [useSeed, setUseSeed] = useState(true)
  const [ledgerFile, setLedgerFile] = useState<File | null>(null)
  const [statementFile, setStatementFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [repro, setRepro] = useState<{ reproducible: boolean; recomputed_hash: string } | null>(null)

  const runRecon = async () => {
    setLoading(true)
    setError(null)
    setRepro(null)
    try {
      const result = useSeed
        ? await api.createRunFromSeed(config.id, actingAs)
        : ledgerFile && statementFile
          ? await api.createRunFromUpload(config.id, actingAs, ledgerFile, statementFile)
          : null
      if (!result) {
        setError('Choose both a ledger and statement CSV, or use the seeded pair.')
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

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            3. Run — {config.recon_name}{' '}
            <Typography component="span" color="text.secondary" variant="body2">
              (v{config.version})
            </Typography>
          </Typography>

          <FormControlLabel
            control={<Switch checked={useSeed} onChange={(e) => setUseSeed(e.target.checked)} />}
            label="Use rehearsed seeded pair (ledger.csv / statement.csv)"
          />

          {!useSeed && (
            <Stack direction="row" spacing={2} sx={{ my: 2 }}>
              <Button component="label" variant="outlined">
                {ledgerFile ? ledgerFile.name : 'Choose ledger CSV'}
                <input
                  type="file"
                  accept=".csv"
                  hidden
                  onChange={(e) => setLedgerFile(e.target.files?.[0] ?? null)}
                />
              </Button>
              <Button component="label" variant="outlined">
                {statementFile ? statementFile.name : 'Choose statement CSV'}
                <input
                  type="file"
                  accept=".csv"
                  hidden
                  onChange={(e) => setStatementFile(e.target.files?.[0] ?? null)}
                />
              </Button>
            </Stack>
          )}

          <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
            <Button variant="contained" onClick={runRecon} disabled={loading}>
              {loading ? 'Running…' : 'Run reconciliation'}
            </Button>
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
    </Stack>
  )
}
