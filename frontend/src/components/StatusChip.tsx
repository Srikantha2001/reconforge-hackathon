import { Chip } from '@mui/material'
import { statusColor } from '../theme'

export function StatusChip({ status }: { status: string }) {
  const color = statusColor[status] ?? '#5B6560'
  return (
    <Chip
      size="small"
      label={status.replaceAll('_', ' ').toLowerCase()}
      sx={{
        backgroundColor: `${color}1A`,
        color,
        border: `1px solid ${color}55`,
        textTransform: 'capitalize',
        fontWeight: 600,
      }}
    />
  )
}
