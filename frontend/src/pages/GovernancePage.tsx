import { Fragment, useEffect, useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Chip, Collapse, Stack, Tab, Table, TableBody,
  TableCell, TableHead, TableRow, Tabs, Typography,
} from '@mui/material'
import { useAuth } from '../context/AuthContext'
import { api, ApiError } from '../api'
import type { AuditLogOut, PendingActionOut, RunOut } from '../types'
import { Figure } from '../components/Figure'

export function GovernancePage({ run: _run }: { run: RunOut | null }) {
  const { role } = useAuth()
  const [tab, setTab] = useState(0)
  return (
    <Stack spacing={2}>
      <Typography variant="h5">Governance</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab label="Checker queue" />
        <Tab label="Audit log" />
      </Tabs>
      {tab === 0 && <CheckerQueue isChecker={role === 'CHECKER' || role === 'ADMIN'} />}
      {tab === 1 && <AuditLog />}
    </Stack>
  )
}

function CheckerQueue({ isChecker }: { isChecker: boolean }) {
  const [pending, setPending] = useState<PendingActionOut[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const reload = () => api.pendingActions().then(setPending).catch(() => setError('Failed to load'))
  useEffect(() => { reload() }, [])

  const decide = async (action_id: number, approved: boolean) => {
    setBusy(action_id)
    setError(null)
    try {
      await api.checkerApprove(action_id, approved)
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Decision failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {pending.length === 0 && <Typography color="text.secondary">No pending governance actions.</Typography>}
        {pending.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Action</TableCell>
                <TableCell>Break</TableCell>
                <TableCell>Maker</TableCell>
                <TableCell>Expires in</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {pending.map((a) => {
                const hours = Math.floor(a.time_remaining_seconds / 3600)
                const urgent = a.time_remaining_seconds < 3600
                return (
                  <TableRow key={a.id} hover>
                    <TableCell><Chip size="small" label={a.action_type.replaceAll('_', ' ').toLowerCase()} /></TableCell>
                    <TableCell><Figure>#{a.break_id}</Figure></TableCell>
                    <TableCell>{a.maker_id}</TableCell>
                    <TableCell sx={{ color: urgent ? 'error.main' : 'text.primary' }}>
                      <Figure>{hours}h {Math.floor((a.time_remaining_seconds % 3600) / 60)}m</Figure>
                    </TableCell>
                    <TableCell align="right">
                      {isChecker ? (
                        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                          <Button size="small" color="success" variant="contained" disabled={busy === a.id}
                                  onClick={() => decide(a.id, true)}>Approve</Button>
                          <Button size="small" color="warning" variant="outlined" disabled={busy === a.id}
                                  onClick={() => decide(a.id, false)}>Reject</Button>
                        </Stack>
                      ) : (
                        <Typography variant="caption" color="text.secondary">checker only</Typography>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function AuditLog() {
  const [entries, setEntries] = useState<AuditLogOut[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  useEffect(() => { api.auditLog(1, 200).then(setEntries).catch(() => {}) }, [])

  return (
    <Card>
      <CardContent>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Actor</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Entity</TableCell>
              <TableCell>Confidence</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {entries.map((e) => (
              <Fragment key={e.id}>
                <TableRow hover sx={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                  <TableCell><Figure sx={{ fontSize: 12 }}>{new Date(e.timestamp).toLocaleString()}</Figure></TableCell>
                  <TableCell>{e.actor_id ?? '—'}</TableCell>
                  <TableCell><Chip size="small" variant="outlined" label={e.action} /></TableCell>
                  <TableCell>{e.entity_type} {e.entity_id && <Figure>#{e.entity_id}</Figure>}</TableCell>
                  <TableCell>{e.confidence != null ? <Figure>{(e.confidence * 100).toFixed(0)}%</Figure> : '—'}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell colSpan={5} sx={{ py: 0, border: 0 }}>
                    <Collapse in={expanded === e.id}>
                      <Box component="pre" sx={{ m: 1, p: 1, bgcolor: '#F1EFE8', borderRadius: 1, fontSize: 11, overflow: 'auto' }}>
                        {JSON.stringify({ before: e.before, after: e.after, reasoning: e.agent_reasoning }, null, 2)}
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
