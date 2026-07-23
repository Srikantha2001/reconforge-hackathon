import { useEffect, useState } from 'react'
import { Box, Button, Chip, Stack, Tooltip, Typography } from '@mui/material'
import DashboardIcon from '@mui/icons-material/SpaceDashboard'
import SettingsIcon from '@mui/icons-material/Tune'
import ShieldIcon from '@mui/icons-material/GppGood'
import BrainIcon from '@mui/icons-material/Psychology'
import GavelIcon from '@mui/icons-material/Gavel'
import BalanceIcon from '@mui/icons-material/AccountBalance'
import PersonIcon from '@mui/icons-material/Person'
import LogoutIcon from '@mui/icons-material/Logout'
import { useAuth } from '../context/AuthContext'
import { api } from '../api'

export const SIDEBAR_WIDTH = 240

export interface NavItem {
  key: string
  label: string
  icon: typeof DashboardIcon
  roles: string[]
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', label: 'Dashboard', icon: DashboardIcon, roles: ['MAKER', 'CHECKER', 'ADMIN'] },
  { key: 'configure', label: 'Configure', icon: SettingsIcon, roles: ['MAKER', 'CHECKER', 'ADMIN'] },
  { key: 'breaks', label: 'Run & breaks', icon: ShieldIcon, roles: ['MAKER', 'CHECKER', 'ADMIN'] },
  { key: 'governance', label: 'Governance', icon: GavelIcon, roles: ['MAKER', 'CHECKER', 'ADMIN'] },
  { key: 'learning', label: 'Learning', icon: BrainIcon, roles: ['MAKER', 'CHECKER', 'ADMIN'] },
  { key: 'regulatory', label: 'Regulatory', icon: BalanceIcon, roles: ['CHECKER', 'DSI', 'ADMIN'] },
  { key: 'client', label: 'Client portal', icon: PersonIcon, roles: ['CLIENT'] },
]

interface SidebarProps {
  active: string
  onSelect: (key: string) => void
}

export function Sidebar({ active, onSelect }: SidebarProps) {
  const { user, logout } = useAuth()
  const [llm, setLlm] = useState<string | null>(null)

  useEffect(() => {
    api.health().then((h) => setLlm(h.llm_provider)).catch(() => setLlm(null))
  }, [])

  const items = NAV_ITEMS.filter((i) => user && i.roles.includes(user.role))

  return (
    <Box
      component="nav"
      sx={{
        width: SIDEBAR_WIDTH, flexShrink: 0, height: '100vh', position: 'sticky', top: 0,
        borderRight: '1px solid', borderColor: 'divider', display: 'flex', flexDirection: 'column',
        px: 1.5, py: 2,
      }}
    >
      <Box sx={{ px: 1, mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: '-0.02em' }}>
          ReconOS
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Deutsche Bank Securities Services
        </Typography>
      </Box>

      <Stack spacing={0.5}>
        {items.map((item) => {
          const Icon = item.icon
          const selected = item.key === active
          return (
            <Stack
              key={item.key}
              direction="row"
              spacing={1.5}
              onClick={() => onSelect(item.key)}
              sx={{
                alignItems: 'center', px: 1.5, py: 1, borderRadius: 1.5, cursor: 'pointer',
                color: selected ? 'primary.main' : 'text.primary',
                bgcolor: selected ? 'rgba(31, 75, 63, 0.1)' : 'transparent',
                fontWeight: selected ? 600 : 400,
                '&:hover': { bgcolor: selected ? 'rgba(31, 75, 63, 0.14)' : 'action.hover' },
              }}
            >
              <Icon fontSize="small" />
              <Typography variant="body2" sx={{ fontWeight: 'inherit' }}>{item.label}</Typography>
            </Stack>
          )
        })}
      </Stack>

      <Box sx={{ flexGrow: 1 }} />

      <Tooltip title={llm === 'stub' ? 'Running fully offline — no LLM key configured' : `LLM provider: ${llm ?? 'unknown'}`}>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', px: 1, mb: 1.5 }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: llm === 'stub' ? 'warning.main' : 'success.main' }} />
          <Typography variant="caption" color="text.secondary">{llm ?? '…'}</Typography>
        </Stack>
      </Tooltip>

      <Box sx={{ px: 1, borderTop: '1px solid', borderColor: 'divider', pt: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, flexGrow: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {user?.email ?? ''}
          </Typography>
          {user?.role && <Chip size="small" label={user.role} color="primary" variant="outlined" />}
        </Stack>
        <Button size="small" fullWidth variant="outlined" startIcon={<LogoutIcon fontSize="small" />} onClick={logout}>
          Log out
        </Button>
      </Box>
    </Box>
  )
}
