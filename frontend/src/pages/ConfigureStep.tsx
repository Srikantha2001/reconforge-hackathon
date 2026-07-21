import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { useActor } from '../context/ActorContext'
import { api, ApiError } from '../api'
import type { ConfigOut, SeedInfo } from '../types'
import { EditableRuleTable } from '../components/EditableRuleTable'
import { VersionChip } from '../components/VersionChip'
import { DoubleRuleTotal } from '../components/DoubleRuleTotal'
import { parseCsvHeader } from '../utils/csv'

interface ConfigureStepProps {
  config: ConfigOut | null
  onConfigChange: (c: ConfigOut) => void
  onApproved: () => void
  useSeed: boolean
  onUseSeedChange: (v: boolean) => void
  sourceFile: File | null
  onSourceFileChange: (f: File | null) => void
  targetFile: File | null
  onTargetFileChange: (f: File | null) => void
}

export function ConfigureStep({
  config,
  onConfigChange,
  onApproved,
  useSeed,
  onUseSeedChange,
  sourceFile,
  onSourceFileChange,
  targetFile,
  onTargetFileChange,
}: ConfigureStepProps) {
  const { actingAs, actingActor } = useActor()
  const [seedInfo, setSeedInfo] = useState<SeedInfo | null>(null)
  const [description, setDescription] = useState(
    'Match ledger to statement exactly on trade id, amount tolerance of 0.01, ' +
      'within 2 days for value date, and account must match exactly.',
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    api.seedInfo().then(setSeedInfo).catch(() => setSeedInfo(null))
  }, [])

  const canAuthor = !loading && (useSeed ? seedInfo?.exists : Boolean(sourceFile && targetFile))

  const author = async () => {
    setLoading(true)
    setError(null)
    try {
      const [columns_a, columns_b] = useSeed
        ? [seedInfo?.ledger_columns ?? [], seedInfo?.statement_columns ?? []]
        : await Promise.all([parseCsvHeader(sourceFile as File), parseCsvHeader(targetFile as File)])
      const cfg = await api.authorConfig({
        nl_description: description,
        actor_id: actingAs,
        columns_a,
        columns_b,
      })
      onConfigChange(cfg)
      setDirty(false)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Failed to author config')
    } finally {
      setLoading(false)
    }
  }

  const saveEdits = async () => {
    if (!config) return
    setLoading(true)
    setError(null)
    try {
      const updated = await api.editConfig(config.id, {
        config_json: config.config_json,
        actor_id: actingAs,
      })
      onConfigChange(updated)
      setDirty(false)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Failed to save edits')
    } finally {
      setLoading(false)
    }
  }

  const approve = async () => {
    if (!config) return
    setLoading(true)
    setError(null)
    try {
      const approved = await api.approveConfig(config.id, actingAs)
      onConfigChange(approved)
      onApproved()
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Failed to approve config')
    } finally {
      setLoading(false)
    }
  }

  const selfApprove = config && config.author_id === actingAs

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            1. Upload source and target files
          </Typography>
          <FormControlLabel
            control={<Switch checked={useSeed} onChange={(e) => onUseSeedChange(e.target.checked)} />}
            label="Use rehearsed seeded pair (ledger.csv / statement.csv)"
          />
          {!useSeed && (
            <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
              <Button component="label" variant="outlined">
                {sourceFile ? sourceFile.name : 'Choose source CSV'}
                <input
                  type="file"
                  accept=".csv"
                  hidden
                  onChange={(e) => onSourceFileChange(e.target.files?.[0] ?? null)}
                />
              </Button>
              <Button component="label" variant="outlined">
                {targetFile ? targetFile.name : 'Choose target CSV'}
                <input
                  type="file"
                  accept=".csv"
                  hidden
                  onChange={(e) => onTargetFileChange(e.target.files?.[0] ?? null)}
                />
              </Button>
            </Stack>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            2. Describe the reconciliation
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The LLM authors a schema-validated config from this — it never matches
            transactions itself. {useSeed && seedInfo?.exists === false && 'Generate seed data first via the API to enable authoring.'}
            {!useSeed && !(sourceFile && targetFile) && 'Choose both files above to enable authoring.'}
          </Typography>
          <TextField
            multiline
            minRows={3}
            fullWidth
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder='e.g. "Match on trade id exactly, amount within 0.01, dates within 2 days"'
          />
          <Stack direction="row" spacing={2} sx={{ mt: 2, alignItems: 'center' }}>
            <Button variant="contained" disabled={!canAuthor} onClick={author}>
              {loading ? 'Authoring…' : 'Author config'}
            </Button>
            {useSeed && seedInfo && (
              <Typography variant="caption" color="text.secondary">
                Columns: {seedInfo.ledger_columns.join(', ')} ↔ {seedInfo.statement_columns.join(', ')}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {config && (
        <Card>
          <CardContent>
            <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="h6">3. Review — {config.recon_name}</Typography>
              <VersionChip version={config.version} status={config.status} />
            </Stack>

            {config.repairs_applied.length > 0 && (
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: 2 }}>
                {config.repairs_applied.map((r, i) => (
                  <Chip key={i} size="small" color="warning" variant="outlined" label={`repaired: ${r}`} />
                ))}
              </Stack>
            )}

            <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
              {config.english_summary}
            </Alert>

            <EditableRuleTable
              rules={config.config_json.match_rules}
              transforms={config.config_json.transforms}
              disabled={config.status === 'approved'}
              onChange={(rules) => {
                onConfigChange({ ...config, config_json: { ...config.config_json, match_rules: rules } })
                setDirty(true)
              }}
            />

            <Stack direction="row" spacing={2} sx={{ mt: 3, alignItems: 'center' }}>
              {config.status === 'draft' && dirty && (
                <Button variant="outlined" onClick={saveEdits} disabled={loading}>
                  Save changes
                </Button>
              )}
              {config.status === 'draft' && (
                <Button
                  variant="contained"
                  color="success"
                  onClick={approve}
                  disabled={loading || dirty || Boolean(selfApprove)}
                >
                  Approve as {actingActor?.display_name.split(' — ')[0] ?? actingAs}
                </Button>
              )}
              {selfApprove && config.status === 'draft' && (
                <Typography variant="caption" color="warning.main">
                  Maker cannot self-approve — switch "acting as" to a different reviewer.
                </Typography>
              )}
              {dirty && (
                <Typography variant="caption" color="text.secondary">
                  Save changes before approving.
                </Typography>
              )}
            </Stack>

            {config.status === 'approved' && (
              <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
                <DoubleRuleTotal
                  label="Approved"
                  value={`v${config.version}`}
                  sublabel={`by ${config.approver_id} · authored by ${config.author_id}`}
                />
              </Box>
            )}
          </CardContent>
        </Card>
      )}
    </Stack>
  )
}
