import { Box, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { Figure } from './Figure'

interface DoubleRuleTotalProps {
  label: string
  value: ReactNode
  sublabel?: string
}

// Signature motif (§14): the accountant's double-rule under a reconciled
// total / approval footer — a thin line then a thicker line, the universal
// "this number is final" mark from paper ledgers.
export function DoubleRuleTotal({ label, value, sublabel }: DoubleRuleTotalProps) {
  return (
    <Box sx={{ display: 'inline-block', minWidth: 220 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline', pb: 1 }}>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5" sx={{ lineHeight: 1 }}>
          <Figure>{value}</Figure>
        </Typography>
      </Stack>
      <Box sx={{ borderTop: '1px solid', borderColor: 'text.primary', opacity: 0.85 }} />
      <Box sx={{ borderTop: '3px solid', borderColor: 'text.primary', mt: '2px' }} />
      {sublabel && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75, textAlign: 'right' }}>
          {sublabel}
        </Typography>
      )}
    </Box>
  )
}
