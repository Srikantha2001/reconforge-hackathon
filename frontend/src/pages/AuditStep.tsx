import { useEffect, useState } from 'react'
import { Button, Card, CardContent, Chip, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { api } from '../api'
import type { AuditLogOut } from '../types'
import { Figure } from '../components/Figure'

export function AuditStep() {
  const [entries, setEntries] = useState<AuditLogOut[]>([])

  const reload = () => api.auditLog({ limit: 200 }).then(setEntries)

  useEffect(() => {
    reload()
  }, [])

  return (
    <Card>
      <CardContent>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6">4. Audit log</Typography>
          <Button size="small" onClick={reload}>
            Refresh
          </Button>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Every action: actor, agent confidence, before/after — the full trail behind
          "human-supervised continuous improvement".
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Actor</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Entity</TableCell>
              <TableCell>Confidence</TableCell>
              <TableCell>Reasoning</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {entries.map((e) => (
              <TableRow key={e.id}>
                <TableCell>
                  <Figure sx={{ fontSize: 12 }}>{new Date(e.timestamp).toLocaleString()}</Figure>
                </TableCell>
                <TableCell>{e.actor_id ?? '—'}</TableCell>
                <TableCell>
                  <Chip size="small" variant="outlined" label={e.action} />
                </TableCell>
                <TableCell>
                  {e.entity_type} {e.entity_id && <Figure>#{e.entity_id}</Figure>}
                </TableCell>
                <TableCell>{e.confidence !== null ? <Figure>{(e.confidence * 100).toFixed(0)}%</Figure> : '—'}</TableCell>
                <TableCell sx={{ maxWidth: 320 }}>
                  <Typography variant="caption" color="text.secondary">
                    {e.agent_reasoning ?? ''}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
