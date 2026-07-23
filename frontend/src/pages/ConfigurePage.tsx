import { useEffect, useState } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Collapse, Divider, MenuItem, Select, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material'
import { useAuth } from '../context/AuthContext'
import { api, ApiError } from '../api'
import type { ConfigOut } from '../types'
import { VersionChip } from '../components/VersionChip'
import { Figure } from '../components/Figure'

interface Props {
  config: ConfigOut | null
  onConfigApproved: (c: ConfigOut) => void
}

export function ConfigurePage({ config, onConfigApproved }: Props) {
  const { role } = useAuth()
  const [configs, setConfigs] = useState<ConfigOut[]>([])
  const [selected, setSelected] = useState<ConfigOut | null>(config)
  const [versions, setVersions] = useState<ConfigOut[]>([])
  const [showJson, setShowJson] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = async (pick?: number) => {
    const list = await api.listConfigs()
    setConfigs(list)
    const chosen = pick ? list.find((c) => c.id === pick) : (selected && list.find((c) => c.id === selected.id)) || list[list.length - 1]
    setSelected(chosen ?? null)
    if (chosen) setVersions(await api.configVersions(chosen.id))
  }

  useEffect(() => {
    reload().catch(() => setError('Failed to load configs'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const act = async (fn: () => Promise<ConfigOut>, approvedHook = false) => {
    setBusy(true)
    setError(null)
    try {
      const cfg = await fn()
      if (approvedHook && cfg.status === 'APPROVED') onConfigApproved(cfg)
      await reload(cfg.id)
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const isMaker = role === 'MAKER' || role === 'ADMIN'
  const isChecker = role === 'CHECKER' || role === 'ADMIN'

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">1. Reconciliation config</Typography>
            {isMaker && (
              <Button variant="contained" disabled={busy} onClick={() => act(() => api.authorConfig(''))}>
                Author new config
              </Button>
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The LLM authors a schema-validated config; it never matches transactions itself.
            Offline it instantiates the pre-approved securities recon.
          </Typography>

          {configs.length > 0 && (
            <Select
              size="small"
              fullWidth
              value={selected?.id ?? ''}
              onChange={(e) => reload(Number(e.target.value))}
              sx={{ mb: 2 }}
            >
              {configs.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.recon_name} — v{c.version} ({c.status})
                </MenuItem>
              ))}
            </Select>
          )}

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          {selected && (
            <Box>
              <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{selected.recon_name}</Typography>
                <VersionChip version={selected.version} status={selected.status} />
              </Stack>
              {selected.english_summary && (
                <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>{selected.english_summary}</Alert>
              )}

              <Button size="small" onClick={() => setShowJson((v) => !v)}>
                {showJson ? 'Hide' : 'Show'} config JSON
              </Button>
              <Collapse in={showJson}>
                <Box
                  component="pre"
                  sx={{
                    mt: 1, p: 1.5, borderRadius: 1, bgcolor: '#1B211D', color: '#E8E4DA',
                    fontSize: 12, overflow: 'auto', maxHeight: 320,
                  }}
                >
                  {JSON.stringify(selected.config_json, null, 2)}
                </Box>
              </Collapse>

              <Divider sx={{ my: 2 }} />
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                {isMaker && selected.status === 'DRAFT' && (
                  <Button variant="outlined" disabled={busy} onClick={() => act(() => api.submitConfig(selected.id))}>
                    Submit for approval
                  </Button>
                )}
                {isChecker && selected.status === 'PENDING_APPROVAL' && (
                  <>
                    <Button variant="contained" color="success" disabled={busy}
                            onClick={() => act(() => api.approveConfig(selected.id, true), true)}>
                      Approve
                    </Button>
                    <Button variant="outlined" color="warning" disabled={busy}
                            onClick={() => act(() => api.approveConfig(selected.id, false))}>
                      Reject
                    </Button>
                  </>
                )}
                {selected.status === 'APPROVED' && (
                  <Alert severity="success" sx={{ py: 0 }}>
                    Approved — ready to run. Author {selected.author_id}, approver {selected.approver_id}.
                  </Alert>
                )}
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>

      {versions.length > 1 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Version history</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Version</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Origin</TableCell>
                  <TableCell>Author</TableCell>
                  <TableCell>Approver</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {versions.map((v) => (
                  <TableRow key={v.id} hover>
                    <TableCell><Figure>v{v.version}</Figure></TableCell>
                    <TableCell><VersionChip version={v.version} status={v.status} /></TableCell>
                    <TableCell>{v.origin}</TableCell>
                    <TableCell>{v.author_id ?? '—'}</TableCell>
                    <TableCell>{v.approver_id ?? '—'}</TableCell>
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
