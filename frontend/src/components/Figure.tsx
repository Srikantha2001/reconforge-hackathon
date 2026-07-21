import { Box, type BoxProps } from '@mui/material'
import { FIGURE_FONT } from '../theme'

// Every numeric value in ReconForge — amounts, percentages, version numbers,
// timestamps, hashes — renders in Spline Sans Mono per the design system
// (§14), distinct from the Schibsted Grotesk UI type used everywhere else.
export function Figure({ children, sx, ...rest }: BoxProps) {
  return (
    <Box
      component="span"
      sx={{ fontFamily: FIGURE_FONT, fontVariantNumeric: 'tabular-nums', ...sx }}
      {...rest}
    >
      {children}
    </Box>
  )
}
