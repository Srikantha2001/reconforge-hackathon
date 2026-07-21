import { useState } from 'react'
import { Box, Container, Step, StepButton, Stepper } from '@mui/material'
import { AppHeader } from './components/AppHeader'
import { ConfigureStep } from './pages/ConfigureStep'
import { RunStep } from './pages/RunStep'
import { BreaksStep } from './pages/BreaksStep'
import { LoopAStep } from './pages/LoopAStep'
import { AuditStep } from './pages/AuditStep'
import type { ConfigOut, RunOut } from './types'

const STEPS = ['Configure', 'Run', 'Breaks', 'Learning loops', 'Audit log']

function App() {
  const [activeStep, setActiveStep] = useState(0)
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const [run, setRun] = useState<RunOut | null>(null)

  const maxStep = run ? 4 : config?.status === 'approved' ? 1 : 0

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppHeader />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stepper nonLinear activeStep={activeStep} sx={{ mb: 4 }}>
          {STEPS.map((label, i) => (
            <Step key={label} completed={i < maxStep}>
              <StepButton onClick={() => i <= maxStep && setActiveStep(i)} disabled={i > maxStep}>
                {label}
              </StepButton>
            </Step>
          ))}
        </Stepper>

        {activeStep === 0 && (
          <ConfigureStep
            config={config}
            onConfigChange={setConfig}
            onApproved={() => setActiveStep(1)}
          />
        )}

        {activeStep === 1 && config && (
          <RunStep
            config={config}
            run={run}
            onRunCreated={(r) => {
              setRun(r)
              setActiveStep(2)
            }}
          />
        )}

        {activeStep === 2 && run && <BreaksStep run={run} />}

        {activeStep === 3 && run && (
          <LoopAStep
            run={run}
            onNewRun={(newRun, newConfig) => {
              setConfig(newConfig)
              setRun(newRun)
            }}
          />
        )}

        {activeStep === 4 && <AuditStep />}
      </Container>
    </Box>
  )
}

export default App
