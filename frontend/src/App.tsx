import { useEffect, useState } from 'react'
import { Box, Container } from '@mui/material'
import { Sidebar, NAV_ITEMS } from './components/Sidebar'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { ConfigurePage } from './pages/ConfigurePage'
import { BreaksPage } from './pages/BreaksPage'
import { GovernancePage } from './pages/GovernancePage'
import { LearningPage } from './pages/LearningPage'
import { RegulatoryPage } from './pages/RegulatoryPage'
import { ClientPortalPage } from './pages/ClientPortalPage'
import { useAuth } from './context/AuthContext'
import { setUnauthorizedHandler } from './api'
import type { ConfigOut, RunOut } from './types'

function defaultPage(role: string): string {
  if (role === 'CLIENT') return 'client'
  if (role === 'DSI') return 'regulatory'
  return 'dashboard'
}

function App() {
  const { isAuthenticated, logout, role } = useAuth()
  const [page, setPage] = useState('dashboard')
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const [run, setRun] = useState<RunOut | null>(null)

  useEffect(() => setUnauthorizedHandler(logout), [logout])
  useEffect(() => {
    if (role) setPage(defaultPage(role))
  }, [role])

  if (!isAuthenticated) return <LoginPage />

  // Guard: if the current page isn't allowed for the role, fall back.
  const allowed = NAV_ITEMS.find((i) => i.key === page && role && i.roles.includes(role))
  const activePage = allowed ? page : defaultPage(role ?? '')

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex' }}>
      <Sidebar active={activePage} onSelect={setPage} />
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Container maxWidth="lg" sx={{ py: 4 }}>
          {activePage === 'dashboard' && (
            <DashboardPage config={config} run={run} onRun={setRun} onGoConfigure={() => setPage('configure')} />
          )}
          {activePage === 'configure' && <ConfigurePage config={config} onConfigApproved={setConfig} />}
          {activePage === 'breaks' && <BreaksPage run={run} />}
          {activePage === 'governance' && <GovernancePage run={run} />}
          {activePage === 'learning' && <LearningPage run={run} onNewConfig={setConfig} />}
          {activePage === 'regulatory' && <RegulatoryPage />}
          {activePage === 'client' && <ClientPortalPage />}
        </Container>
      </Box>
    </Box>
  )
}

export default App
