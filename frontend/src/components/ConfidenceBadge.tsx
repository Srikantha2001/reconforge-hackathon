import { Chip, Tooltip } from '@mui/material'
import { Figure } from './Figure'

interface ConfidenceBadgeProps {
  confidence: number
  threshold?: number
}

// Autonomy dial (§8 CORE): a confidence badge that visually distinguishes
// "would auto-accept" from "routes to a human" at the given STP threshold.
export function ConfidenceBadge({ confidence, threshold = 0.9 }: ConfidenceBadgeProps) {
  const autoAccept = confidence >= threshold
  return (
    <Tooltip
      title={
        autoAccept
          ? `>= threshold (${threshold.toFixed(2)}) — would auto-accept`
          : `< threshold (${threshold.toFixed(2)}) — routes to a human`
      }
    >
      <Chip
        size="small"
        label={<Figure>{(confidence * 100).toFixed(0)}%</Figure>}
        color={autoAccept ? 'success' : 'warning'}
        variant={autoAccept ? 'filled' : 'outlined'}
      />
    </Tooltip>
  )
}
