import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Stack, Chip, TextField } from '@mui/material'
import type { MatchRule, Transform } from '../types'

interface EditableRuleTableProps {
  rules: MatchRule[]
  transforms: Transform[]
  onChange: (rules: MatchRule[]) => void
  disabled?: boolean
}

// Used during config review, before approval — the human can tweak a
// tolerance and re-approve (demo script step 2: "maker-checker visible").
export function EditableRuleTable({ rules, transforms, onChange, disabled }: EditableRuleTableProps) {
  const updateRule = (i: number, patch: Partial<MatchRule>) => {
    const next = rules.slice()
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }

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
              <TableCell>Tolerance</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rules.map((r, i) => (
              <TableRow key={i}>
                <TableCell>{r.field_a}</TableCell>
                <TableCell>{r.field_b}</TableCell>
                <TableCell>
                  <Chip size="small" label={r.type} />
                </TableCell>
                <TableCell>
                  {r.type === 'numeric_tolerance' && (
                    <TextField
                      size="small"
                      type="number"
                      value={r.tolerance ?? 0}
                      disabled={disabled}
                      onChange={(e) => updateRule(i, { tolerance: parseFloat(e.target.value) })}
                      slotProps={{ htmlInput: { step: 0.01, style: { width: 90 } } }}
                    />
                  )}
                  {r.type === 'date_tolerance' && (
                    <TextField
                      size="small"
                      type="number"
                      value={r.tolerance_days ?? 0}
                      disabled={disabled}
                      onChange={(e) => updateRule(i, { tolerance_days: parseInt(e.target.value, 10) })}
                      slotProps={{ htmlInput: { step: 1, style: { width: 70 } } }}
                      helperText="days"
                    />
                  )}
                  {r.type === 'exact' && '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  )
}
