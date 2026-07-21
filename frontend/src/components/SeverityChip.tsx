import { Chip } from '@mui/material'
import { severityColor } from '../theme'

export function SeverityChip({ severity }: { severity: string }) {
  const color = severityColor[severity as keyof typeof severityColor] ?? '#5B6560'
  return (
    <Chip
      size="small"
      label={severity}
      sx={{
        backgroundColor: `${color}1A`,
        color,
        border: `1px solid ${color}55`,
        textTransform: 'capitalize',
      }}
    />
  )
}
