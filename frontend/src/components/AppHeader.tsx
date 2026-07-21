import { useEffect, useState } from 'react'
import { AppBar, Box, MenuItem, Select, Stack, Toolbar, Tooltip, Typography } from '@mui/material'
import { useActor } from '../context/ActorContext'
import { api } from '../api'

export function AppHeader() {
  const { actors, actingAs, setActingAs } = useActor()
  const [llmProvider, setLlmProvider] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then((h) => setLlmProvider(h.llm_provider))
      .catch(() => setLlmProvider(null))
  }, [])

  return (
    <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
      <Toolbar sx={{ gap: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: '-0.02em' }}>
          ReconForge
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>
          Author from words. Run with control-grade determinism.
        </Typography>
        <Box sx={{ flexGrow: 1 }} />

        <Tooltip title={llmProvider === 'stub' ? 'Running fully offline — no LLM key configured' : `LLM provider: ${llmProvider ?? 'unknown'}`}>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', mr: 1 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: llmProvider === 'stub' ? 'warning.main' : 'success.main',
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {llmProvider ?? '…'}
            </Typography>
          </Stack>
        </Tooltip>

        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="caption" color="text.secondary">
            Acting as
          </Typography>
          <Select
            size="small"
            value={actingAs}
            onChange={(e) => setActingAs(e.target.value)}
            sx={{ minWidth: 220 }}
          >
            {actors.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.display_name}
              </MenuItem>
            ))}
          </Select>
        </Stack>
      </Toolbar>
    </AppBar>
  )
}
