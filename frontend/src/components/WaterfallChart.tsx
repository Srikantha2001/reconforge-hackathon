import { Box, Card, CardContent, Stack, Tooltip, Typography } from '@mui/material'
import { Figure } from './Figure'
import type { PassStatOut } from '../types'

// Hand-rolled stacked bars (matched vs still-in-pool) per pass — keeps deps
// lean and matches the design system. Height encodes the pool entering each
// pass; the green segment is what that pass matched.
export function WaterfallChart({ passes }: { passes: PassStatOut[] }) {
  const maxPool = Math.max(1, ...passes.map((p) => p.matched_count + p.pool_a_remaining))

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Matching waterfall — 7 passes
        </Typography>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-end', height: 180, mt: 2 }}>
          {passes.map((p) => {
            const entering = p.matched_count + p.pool_a_remaining
            const barH = (entering / maxPool) * 150
            const matchedFrac = entering ? p.matched_count / entering : 0
            return (
              <Tooltip
                key={p.pass_number}
                title={`Pass ${p.pass_number}: ${p.pass_name} — matched ${p.matched_count}, ${p.pool_a_remaining} remaining`}
              >
                <Stack sx={{ flex: 1, alignItems: 'center' }}>
                  <Typography variant="caption" sx={{ mb: 0.5 }}>
                    <Figure sx={{ fontWeight: 700, color: 'success.main' }}>{p.matched_count}</Figure>
                  </Typography>
                  <Box
                    sx={{
                      width: '100%',
                      maxWidth: 48,
                      height: Math.max(barH, 6),
                      borderRadius: 1,
                      overflow: 'hidden',
                      display: 'flex',
                      flexDirection: 'column',
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Box sx={{ height: `${matchedFrac * 100}%`, backgroundColor: 'success.main' }} />
                    <Box sx={{ flexGrow: 1, backgroundColor: 'warning.light', opacity: 0.5 }} />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                    P{p.pass_number}
                  </Typography>
                </Stack>
              </Tooltip>
            )
          })}
        </Stack>
        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
          <Legend color="success.main" label="matched by pass" />
          <Legend color="warning.light" label="carried to next pass" />
        </Stack>
      </CardContent>
    </Card>
  )
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
      <Box sx={{ width: 10, height: 10, borderRadius: 0.5, backgroundColor: color }} />
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Stack>
  )
}
