import { useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, MenuItem, Select, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, Typography,
} from '@mui/material'
import { api, ApiError } from '../api'
import type { ClientReconOut, EvidencePack } from '../types'
import { Figure } from '../components/Figure'

export function ClientPortalPage() {
  const [fund, setFund] = useState('FUND_A')
  const [file, setFile] = useState<File | null>(null)
  const [recon, setRecon] = useState<ClientReconOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const upload = async () => {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const res = await api.clientUpload(fund, 'POSITION', file)
      setRecon(await api.clientRecon(res.run_id))
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Upload failed')
    } finally { setBusy(false) }
  }

  const downloadEvidence = async () => {
    if (!recon) return
    const pack: EvidencePack = await api.clientEvidence(recon.run_id)
    const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `evidence_pack_run_${recon.run_id}.json`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Box sx={{ maxWidth: 760, mx: 'auto' }}>
      <Typography variant="h5" gutterBottom>Reconcile your portfolio</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Upload your internal position file to reconcile against Deutsche Bank's records.
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack spacing={2}>
            <Select size="small" value={fund} onChange={(e) => setFund(e.target.value)}>
              <MenuItem value="FUND_A">FUND_A — Alpha Capital Main Fund</MenuItem>
              <MenuItem value="FUND_B">FUND_B — Beta Equity Fund</MenuItem>
              <MenuItem value="FUND_C">FUND_C — Gamma</MenuItem>
            </Select>
            <Button component="label" variant="outlined">
              {file ? file.name : 'Choose position file (CSV)'}
              <input type="file" accept=".csv" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Button>
            <Button variant="contained" onClick={upload} disabled={!file || busy}>
              {busy ? 'Reconciling…' : 'Reconcile'}
            </Button>
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </CardContent>
      </Card>

      {recon && (
        <>
          <Card sx={{ mb: 3 }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">Match rate</Typography>
              <Typography variant="h2" sx={{ color: 'success.main' }}>
                <Figure>{recon.match_rate.toFixed(0)}%</Figure>
              </Typography>
              <Stack direction="row" spacing={2} sx={{ justifyContent: 'center', mt: 2 }}>
                <Stat label="Matched" value={recon.matched_count} />
                <Stat label="Open breaks" value={recon.break_count} />
              </Stack>
              <Button variant="outlined" sx={{ mt: 2 }} onClick={downloadEvidence}>Download evidence pack</Button>
            </CardContent>
          </Card>

          {recon.breaks.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Items to review</Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>ISIN</TableCell>
                      <TableCell>Issue</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Amount</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {recon.breaks.map((b) => (
                      <TableRow key={b.break_id}>
                        <TableCell><Figure>{b.isin}</Figure></TableCell>
                        <TableCell>{b.issue}</TableCell>
                        <TableCell>{b.status}</TableCell>
                        <TableCell align="right"><Figure>{b.amount?.toLocaleString() ?? '—'}</Figure></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </Box>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Stack sx={{ alignItems: 'center' }}>
      <Typography variant="h5"><Figure>{value}</Figure></Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Stack>
  )
}
