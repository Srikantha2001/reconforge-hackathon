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
import type { ConfigOut, LoopAAggregateGroup, LoopAWhatIfOut, ResolutionMemoryOut, RunOut } from '../types'
import { Figure } from '../components/Figure'
import { VersionChip } from '../components/VersionChip'
import { ARCHETYPE_LABELS } from '../types'

interface LoopAStepProps {
  run: RunOut
  onNewRun: (run: RunOut, config: ConfigOut) => void
}

export function LoopAStep({ run, onNewRun }: LoopAStepProps) {
  const { actingAs, actingActor } = useActor()
  const [groups, setGroups] = useState<LoopAAggregateGroup[]>([])
  const [proposal, setProposal] = useState<{ new_config: ConfigOut; rationale: string } | null>(null)
  const [whatIf, setWhatIf] = useState<LoopAWhatIfOut | null>(null)
  const [memory, setMemory] = useState<ResolutionMemoryOut[]>([])
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = () => {
    api.loopAAggregate(run.id).then(setGroups)
    api.resolutionMemory().then(setMemory)
  }

  useEffect(reload, [run.id])

  const propose = async (g: LoopAAggregateGroup) => {
    setLoading('propose')
    setError(null)
    setWhatIf(null)
    try {
      const result = await api.loopAPropose(run.id, {
        actor_id: actingAs,
        field_a: g.field_a,
        field_b: g.field_b,
        type: g.type,
      })
      setProposal(result)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Propose failed')
    } finally {
      setLoading(null)
    }
  }

  const previewWhatIf = async () => {
    if (!proposal) return
    setLoading('whatif')
    setError(null)
    try {
      setWhatIf(await api.loopAWhatIf(run.id, proposal.new_config.id))
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'What-if failed')
    } finally {
      setLoading(null)
    }
  }

  const approveAndRerun = async () => {
    if (!proposal) return
    setLoading('approve')
    setError(null)
    try {
      const approved = await api.approveConfig(proposal.new_config.id, actingAs)
      const newRun = await api.createRunFromSeed(approved.id, actingAs)
      onNewRun(newRun, approved)
      setProposal(null)
      setWhatIf(null)
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Approve/re-run failed')
    } finally {
      setLoading(null)
    }
  }

  const selfApprove = proposal && proposal.new_config.author_id === actingAs

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            5. Learning loops
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Loop A: manually-matched breaks are aggregated by which rule disagreed; if a
            pattern is systemic, propose widening that rule — through the same maker-checker
            gate as initial authoring. Nothing changes silently.
          </Typography>

          {groups.length === 0 && (
            <Alert severity="info" variant="outlined">
              No manually-matched breaks yet for this run. Go to the Breaks board and use
              "Manual match" on a two-sided break (e.g. the drift-cluster breaks) to build a
              signal here.
            </Alert>
          )}

          {groups.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Rule</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Observed deltas</TableCell>
                  <TableCell>Count</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {groups.map((g, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      {g.field_a} ↔ {g.field_b}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={g.type} />
                    </TableCell>
                    <TableCell>
                      <Figure>{g.observed_deltas.join(', ')}</Figure>
                    </TableCell>
                    <TableCell>
                      <Figure>{g.count}</Figure>
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => propose(g)} disabled={Boolean(loading)}>
                        {loading === 'propose' ? 'Proposing…' : 'Propose config change'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>

      {proposal && (
        <Card>
          <CardContent>
            <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="h6">Proposed change</Typography>
              <VersionChip version={proposal.new_config.version} status={proposal.new_config.status} />
            </Stack>
            <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
              {proposal.rationale}
            </Alert>

            <Stack direction="row" spacing={2}>
              <Button variant="outlined" onClick={previewWhatIf} disabled={Boolean(loading)}>
                {loading === 'whatif' ? 'Computing…' : 'Preview what-if'}
              </Button>
            </Stack>

            {whatIf && (
              <Stack spacing={1} sx={{ mt: 2 }}>
                <Divider />
                <Stack direction="row" spacing={4} sx={{ mt: 1 }}>
                  <Stack>
                    <Typography variant="caption" color="text.secondary">
                      Current match rate
                    </Typography>
                    <Typography variant="h5">
                      <Figure>{(whatIf.current_match_rate * 100).toFixed(1)}%</Figure>
                    </Typography>
                  </Stack>
                  <Stack>
                    <Typography variant="caption" color="text.secondary">
                      Candidate match rate
                    </Typography>
                    <Typography variant="h5" color="success.main">
                      <Figure>{(whatIf.candidate_match_rate * 100).toFixed(1)}%</Figure>
                    </Typography>
                  </Stack>
                </Stack>
                <Typography variant="body2" color="success.main">
                  Auto-matches <Figure>{whatIf.newly_matched_keys.length}</Figure>, risks{' '}
                  <Figure>{whatIf.newly_broken_keys.length}</Figure>
                </Typography>
                {whatIf.newly_broken_keys.length > 0 && (
                  <Alert severity="warning" variant="outlined">
                    Newly broken (never hidden): {whatIf.newly_broken_keys.join(', ')}
                  </Alert>
                )}

                <Stack direction="row" spacing={2} sx={{ mt: 2, alignItems: 'center' }}>
                  <Button
                    variant="contained"
                    color="success"
                    onClick={approveAndRerun}
                    disabled={Boolean(loading) || Boolean(selfApprove)}
                  >
                    {loading === 'approve'
                      ? 'Approving…'
                      : `Approve as ${actingActor?.display_name.split(' — ')[0] ?? actingAs} & re-run`}
                  </Button>
                  {selfApprove && (
                    <Typography variant="caption" color="warning.main">
                      Maker cannot self-approve — switch "acting as" to a different reviewer.
                    </Typography>
                  )}
                </Stack>
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      {memory.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Loop B — resolution memory
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Archetype</TableCell>
                  <TableCell>Resolution</TableCell>
                  <TableCell>Confidence</TableCell>
                  <TableCell>Times seen</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {memory.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{ARCHETYPE_LABELS[m.archetype] ?? m.archetype}</TableCell>
                    <TableCell>{m.resolution}</TableCell>
                    <TableCell>
                      <Figure>{(m.confidence * 100).toFixed(0)}%</Figure>
                    </TableCell>
                    <TableCell>
                      <Figure>{m.times_seen}</Figure>
                    </TableCell>
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
