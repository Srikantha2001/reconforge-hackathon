import { Box, Stack, Typography } from '@mui/material'
import { Figure } from './Figure'

interface SplitMatchedBarProps {
  matched: number
  breaks: number
  label?: string
}

// Signature motif (§14): a split matched/unmatched bar instead of a plain
// progress bar — the point is to make the *break* portion legible, not just
// show "percent done".
export function SplitMatchedBar({ matched, breaks, label }: SplitMatchedBarProps) {
  const total = matched + breaks || 1
  const matchedPct = (matched / total) * 100
  const breaksPct = 100 - matchedPct

  return (
    <Box sx={{ width: '100%' }}>
      {label && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
          {label}
        </Typography>
      )}
      <Box
        sx={{
          display: 'flex',
          height: 10,
          borderRadius: 999,
          overflow: 'hidden',
          border: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Box sx={{ width: `${matchedPct}%`, backgroundColor: 'success.main' }} />
        <Box sx={{ width: `${breaksPct}%`, backgroundColor: 'warning.main' }} />
      </Box>
      <Stack direction="row" sx={{ justifyContent: 'space-between', mt: 0.75 }}>
        <Typography variant="body2" color="text.secondary">
          <Figure sx={{ color: 'success.main', fontWeight: 600 }}>{matched}</Figure> matched
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <Figure sx={{ color: 'warning.main', fontWeight: 600 }}>{breaks}</Figure> breaks
        </Typography>
      </Stack>
    </Box>
  )
}
