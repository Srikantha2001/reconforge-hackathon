import { Box, Stack, Typography } from '@mui/material'
import { Figure } from './Figure'
import type { RootCauseTree as Tree } from '../types'

// The showstopper break UI: three stacked layers — the data, the rule that
// failed, and the AI diagnosis — each in its own bordered box.
export function RootCauseTree({ tree }: { tree: Tree }) {
  return (
    <Stack spacing={1.5}>
      <Layer color="#185FA5" title="Data layer">
        <Typography variant="body2">{tree.data_layer.summary}</Typography>
        {tree.data_layer.isin && (
          <Typography variant="caption" color="text.secondary">
            ISIN <Figure>{tree.data_layer.isin}</Figure>
          </Typography>
        )}
      </Layer>

      <Layer color="#534AB7" title="Rule layer">
        <Typography variant="body2">
          Failed at pass <Figure>{tree.rule_that_failed.pass ?? '—'}</Figure> on field{' '}
          <Figure>{tree.rule_that_failed.field}</Figure>
        </Typography>
        {Object.entries(tree.rule_that_failed.deltas || {}).map(([k, v]) => (
          <Typography key={k} variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {k}: <Figure>{String(v)}</Figure>
          </Typography>
        ))}
      </Layer>

      <Layer color="#D85A30" title="AI diagnosis">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {tree.ai_diagnosis.primary_hypothesis}
        </Typography>
        {tree.ai_diagnosis.evidence.length > 0 && (
          <Box component="ul" sx={{ m: 0.5, pl: 2.5 }}>
            {tree.ai_diagnosis.evidence.map((e, i) => (
              <Typography key={i} component="li" variant="caption" color="text.secondary">
                {e}
              </Typography>
            ))}
          </Box>
        )}
        {tree.ai_diagnosis.alternative && (
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
            Alternative: {tree.ai_diagnosis.alternative}
          </Typography>
        )}
      </Layer>
    </Stack>
  )
}

function Layer({ color, title, children }: { color: string; title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ border: `1.5px solid ${color}`, borderRadius: 1.5, p: 1.5 }}>
      <Typography variant="caption" sx={{ color, fontWeight: 700, letterSpacing: '0.04em' }}>
        {title.toUpperCase()}
      </Typography>
      <Box sx={{ mt: 0.5 }}>{children}</Box>
    </Box>
  )
}
