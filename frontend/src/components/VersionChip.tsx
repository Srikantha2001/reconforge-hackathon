import { Box, Chip, type ChipProps } from '@mui/material'
import { Figure } from './Figure'
import { statusColor } from '../theme'

interface VersionChipProps {
  version: number | string
  status: string
  size?: ChipProps['size']
}

// Signature motif (§14): a version chip + status dot on every config/run.
export function VersionChip({ version, status, size = 'small' }: VersionChipProps) {
  const color = statusColor[status as keyof typeof statusColor] ?? '#5B6560'
  return (
    <Chip
      size={size}
      variant="outlined"
      label={
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Box
            component="span"
            sx={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }}
          />
          <Figure>v{version}</Figure>
          <Box component="span" sx={{ opacity: 0.7 }}>
            · {status}
          </Box>
        </Box>
      }
      sx={{ borderColor: 'divider' }}
    />
  )
}
