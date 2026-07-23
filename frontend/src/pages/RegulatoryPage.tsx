import { Fragment, useEffect, useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Collapse, Stack, Tab, Table, TableBody, TableCell,
  TableHead, TableRow, Tabs, Typography,
} from '@mui/material'
import { api, ApiError } from '../api'
import type { CassReconciliationOut, RegulatoryNotificationOut } from '../types'
import { Figure } from '../components/Figure'
import { StatusChip } from '../components/StatusChip'

export function RegulatoryPage() {
  const [tab, setTab] = useState(0)
  return (
    <Stack spacing={2}>
      <Typography variant="h5">Regulatory</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab label="EMIR" /><Tab label="CASS 7A" /><Tab label="CSDR" />
      </Tabs>
      {tab === 0 && <EmirTab />}
      {tab === 1 && <CassTab />}
      {tab === 2 && <CsdrTab />}
    </Stack>
  )
}

function EmirTab() {
  const [notifs, setNotifs] = useState<RegulatoryNotificationOut[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = () => Promise.all([api.emirNotifications('DRAFT'), api.emirNotifications('FILED')])
    .then(([d, f]) => setNotifs([...d, ...f])).catch(() => setError('Failed to load'))
  useEffect(() => { reload() }, [])

  const file = async (id: number) => {
    setError(null)
    try { await api.approveEmir(id); reload() }
    catch (e) { setError(e instanceof ApiError ? String(e.message) : 'File failed') }
  }

  return (
    <Card>
      <CardContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {notifs.length === 0 && <Typography color="text.secondary">No EMIR notifications.</Typography>}
        {notifs.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Break</TableCell>
                <TableCell>Amount (EUR)</TableCell>
                <TableCell>Days</TableCell>
                <TableCell>Authority</TableCell>
                <TableCell>Status</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {notifs.map((n) => {
                const bigAmt = (n.dispute_amount ?? 0) > 15_000_000
                const bigDays = (n.dispute_days ?? 0) > 15
                return (
                  <Fragment key={n.id}>
                    <TableRow hover sx={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === n.id ? null : n.id)}>
                      <TableCell><Figure>#{n.break_id}</Figure></TableCell>
                      <TableCell sx={{ color: bigAmt ? 'error.main' : 'text.primary' }}>
                        <Figure>{(n.dispute_amount ?? 0).toLocaleString()}</Figure>
                      </TableCell>
                      <TableCell sx={{ color: bigDays ? 'error.main' : 'text.primary' }}><Figure>{n.dispute_days}</Figure></TableCell>
                      <TableCell>{n.competent_authority}</TableCell>
                      <TableCell><StatusChip status={n.status} /></TableCell>
                      <TableCell align="right">
                        {n.status === 'DRAFT' && (
                          <Button size="small" variant="contained" onClick={(e) => { e.stopPropagation(); file(n.id) }}>
                            Approve &amp; file
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell colSpan={6} sx={{ py: 0, border: 0 }}>
                        <Collapse in={expanded === n.id}>
                          <Alert severity="warning" variant="outlined" sx={{ my: 1 }}>{n.notification_draft}</Alert>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function CassTab() {
  const [date] = useState('2024-01-15')
  const [recon, setRecon] = useState<CassReconciliationOut | null>(null)
  const [pack, setPack] = useState<Record<string, unknown> | null>(null)

  useEffect(() => { api.cassDaily(date).then(setRecon).catch(() => {}) }, [date])

  const download = async () => {
    const p = await api.cassResolutionPack(date)
    setPack(p)
    const blob = new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `cass_resolution_${date}.json`; a.click()
    URL.revokeObjectURL(url)
  }

  if (!recon) return <Card><CardContent><Typography color="text.secondary">Loading…</Typography></CardContent></Card>
  const shortfall = recon.shortfall_amount ?? 0

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>CASS 7A daily — {recon.reconciliation_date}</Typography>
        <Stack direction="row" spacing={4} sx={{ my: 2, flexWrap: 'wrap' }}>
          <Metric label="Client liability" value={recon.client_liability_total.toLocaleString()} />
          <Metric label="Safeguarded funds" value={recon.safeguarded_funds_total.toLocaleString()} />
          <Metric label="Shortfall" value={shortfall.toLocaleString()} accent={shortfall > 0 ? '#B3261E' : undefined} />
        </Stack>
        <StatusChip status={recon.shortfall_status} />
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined" onClick={download}>Download resolution pack</Button>
        </Box>
        {pack && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            document_hash: <Figure>{String((pack as { document_hash?: string }).document_hash ?? '').slice(0, 24)}…</Figure>
          </Typography>
        )}
      </CardContent>
    </Card>
  )
}

function CsdrTab() {
  const [rows, setRows] = useState<unknown[]>([])
  useEffect(() => { api.csdr().then(setRows).catch(() => {}) }, [])
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>CSDR settlement penalties</Typography>
        {rows.length === 0
          ? <Alert severity="success" variant="outlined">No settlement fails — no CSDR penalties outstanding.</Alert>
          : <Typography>{rows.length} penalties</Typography>}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <Stack>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h6" sx={{ color: accent ?? 'text.primary' }}><Figure>{value}</Figure></Typography>
    </Stack>
  )
}
