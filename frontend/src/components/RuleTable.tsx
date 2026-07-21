import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography, Paper, Stack, Chip } from '@mui/material'
import { Figure } from './Figure'
import type { MatchRule, Transform } from '../types'

function ruleDescription(r: MatchRule): string {
  if (r.type === 'exact') return 'must match exactly'
  if (r.type === 'numeric_tolerance') return `within ±${r.tolerance}`
  if (r.type === 'date_tolerance') return `within ${r.tolerance_days} day(s)`
  return r.type
}

export function RuleTable({ rules, transforms }: { rules: MatchRule[]; transforms: Transform[] }) {
  return (
    <Stack spacing={1.5}>
      {transforms.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          {transforms.map((t, i) => (
            <Chip key={i} size="small" variant="outlined" label={`${t.op}(${t.field})`} />
          ))}
        </Stack>
      )}
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Field A</TableCell>
              <TableCell>Field B</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Rule</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rules.map((r, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontFamily: 'inherit' }}>
                    {r.field_a}
                  </Typography>
                </TableCell>
                <TableCell>{r.field_b}</TableCell>
                <TableCell>
                  <Chip size="small" label={r.type} />
                </TableCell>
                <TableCell>
                  <Figure sx={{ fontSize: 13 }}>{ruleDescription(r)}</Figure>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  )
}
