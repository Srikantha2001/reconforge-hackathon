import { useEffect, useState } from 'react'
import { Box, MenuItem, Select, Stack, Tooltip, Typography } from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import AutorenewIcon from '@mui/icons-material/Autorenew'
import HistoryIcon from '@mui/icons-material/History'
import { useActor } from '../context/ActorContext'
import { api } from '../api'

export const SIDEBAR_WIDTH = 240

const STEP_ICONS = [UploadFileIcon, PlayArrowIcon, AutorenewIcon, HistoryIcon]

interface SidebarProps {
  steps: string[]
  activeStep: number
  maxStep: number
  onSelect: (i: number) => void
}

export function Sidebar({ steps, activeStep, maxStep, onSelect }: SidebarProps) {
  const { actors, actingAs, setActingAs } = useActor()
  const [llmProvider, setLlmProvider] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then((h) => setLlmProvider(h.llm_provider))
      .catch(() => setLlmProvider(null))
  }, [])

  return (
    <Box
      component="nav"
      sx={{
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        height: '100vh',
        position: 'sticky',
        top: 0,
        borderRight: '1px solid',
        borderColor: 'divider',
        display: 'flex',
        flexDirection: 'column',
        px: 1.5,
        py: 2,
      }}
    >
      <Box sx={{ px: 1, mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: '-0.02em' }}>
          ReconForge
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Author from words. Run with control-grade determinism.
        </Typography>
      </Box>

      <Stack spacing={0.5}>
        {steps.map((label, i) => {
          const Icon = STEP_ICONS[i]
          const disabled = i > maxStep
          const selected = i === activeStep
          return (
            <Stack
              key={label}
              direction="row"
              spacing={1.5}
              onClick={() => !disabled && onSelect(i)}
              sx={{
                alignItems: 'center',
                px: 1.5,
                py: 1,
                borderRadius: 1.5,
                cursor: disabled ? 'default' : 'pointer',
                color: disabled ? 'text.disabled' : selected ? 'primary.main' : 'text.primary',
                bgcolor: selected ? 'rgba(31, 75, 63, 0.1)' : 'transparent',
                fontWeight: selected ? 600 : 400,
                '&:hover': disabled ? undefined : { bgcolor: selected ? 'rgba(31, 75, 63, 0.14)' : 'action.hover' },
              }}
            >
              <Icon fontSize="small" />
              <Typography variant="body2" sx={{ fontWeight: 'inherit' }}>
                {label}
              </Typography>
            </Stack>
          )
        })}
      </Stack>

      <Box sx={{ flexGrow: 1 }} />

      <Tooltip title={llmProvider === 'stub' ? 'Running fully offline — no LLM key configured' : `LLM provider: ${llmProvider ?? 'unknown'}`}>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', px: 1, mb: 1.5 }}>
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

      <Box sx={{ px: 1 }}>
        <Typography variant="caption" color="text.secondary">
          Acting as
        </Typography>
        <Select
          size="small"
          fullWidth
          value={actingAs}
          onChange={(e) => setActingAs(e.target.value)}
          sx={{ mt: 0.5 }}
        >
          {actors.map((a) => (
            <MenuItem key={a.id} value={a.id}>
              {a.display_name}
            </MenuItem>
          ))}
        </Select>
      </Box>
    </Box>
  )
}
