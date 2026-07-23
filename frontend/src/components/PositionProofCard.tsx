import { useState } from 'react'
import { Alert, Box, Button, Card, CardContent, IconButton, Stack, Tooltip, Typography } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { Figure } from './Figure'
import { api } from '../api'
import type { PositionProofOut, RunOut } from '../types'

const PROOF_COLOR: Record<string, string> = {
  PROVED: '#2E7D46',
  PARTIAL: '#B4790A',
  UNPROVED: '#B3261E',
  NOT_APPLICABLE: '#5B6560',
}

export function PositionProofCard({ run, proof }: { run: RunOut; proof: PositionProofOut | null }) {
  const [repro, setRepro] = useState<{ reproducible: boolean } | null>(null)
  const [reproLoading, setReproLoading] = useState(false)
  const status = proof?.status ?? run.position_proof_status ?? 'UNKNOWN'
  const color = PROOF_COLOR[status] ?? '#5B6560'

  const checkRepro = async () => {
    setReproLoading(true)
    try {
      setRepro(await api.reproduce(run.id))
    } finally {
      setReproLoading(false)
    }
  }

  return (
    <Card>
      <CardContent>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">Position proof</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Box sx={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: color }} />
            <Typography sx={{ fontWeight: 700, color }}>{status}</Typography>
          </Stack>
        </Stack>

        {proof && proof.status !== 'NOT_APPLICABLE' && (
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 2, flexWrap: 'wrap' }}>
            <ProofCell label="Opening" value={proof.opening} />
            <Typography variant="h5" color="text.secondary">+</Typography>
            <ProofCell label="Net movement" value={proof.computed_closing - proof.opening} />
            <Typography variant="h5" color="text.secondary">=</Typography>
            <ProofCell label="Closing" value={proof.stated_closing} />
            <Box sx={{ flexGrow: 1 }} />
            <ProofCell label="Variance" value={proof.variance} highlight={proof.variance !== 0} />
          </Stack>
        )}

        <Box sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Output hash — same input → identical hash, every run
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Figure sx={{ fontSize: 13 }}>{run.output_hash.slice(0, 24)}…</Figure>
            <Tooltip title="Copy full hash">
              <IconButton size="small" onClick={() => navigator.clipboard?.writeText(run.output_hash)}>
                <ContentCopyIcon sx={{ fontSize: 14 }} />
              </IconButton>
            </Tooltip>
          </Stack>

          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mt: 1.5 }}>
            <Button variant="outlined" size="small" onClick={checkRepro} disabled={reproLoading}>
              {reproLoading ? 'Verifying…' : 'Reproduce'}
            </Button>
            {repro && (
              <Alert severity={repro.reproducible ? 'success' : 'error'} sx={{ py: 0 }}>
                {repro.reproducible
                  ? 'PASS — same input, same output. A control, not a guess.'
                  : 'FAIL — hash mismatch, investigate immediately.'}
              </Alert>
            )}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  )
}

function ProofCell({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <Stack>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" sx={{ color: highlight ? 'error.main' : 'text.primary' }}>
        <Figure>{value.toLocaleString()}</Figure>
      </Typography>
    </Stack>
  )
}
