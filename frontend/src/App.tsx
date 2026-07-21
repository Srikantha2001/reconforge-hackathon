import { useState } from 'react'
import { Box, Container } from '@mui/material'
import { Sidebar } from './components/Sidebar'
import { ConfigureStep } from './pages/ConfigureStep'
import { RunStep } from './pages/RunStep'
import { LoopAStep } from './pages/LoopAStep'
import { AuditStep } from './pages/AuditStep'
import type { ConfigOut, RunOut } from './types'

const STEPS = ['Configure', 'Run & breaks', 'Learning loops', 'Audit log']

function App() {
  const [activeStep, setActiveStep] = useState(0)
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const [run, setRun] = useState<RunOut | null>(null)

  // Files are uploaded once, up front in Configure (design-time: only their
  // column names are used, to author the config) and reused as-is by Run
  // (run-time: their full contents are matched) — no re-upload needed.
  const [useSeed, setUseSeed] = useState(true)
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [targetFile, setTargetFile] = useState<File | null>(null)

  const maxStep = run ? 3 : config?.status === 'approved' ? 1 : 0

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex' }}>
      <Sidebar steps={STEPS} activeStep={activeStep} maxStep={maxStep} onSelect={setActiveStep} />
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Container maxWidth="lg" sx={{ py: 4 }}>
          {activeStep === 0 && (
            <ConfigureStep
              config={config}
              onConfigChange={setConfig}
              onApproved={() => setActiveStep(1)}
              useSeed={useSeed}
              onUseSeedChange={setUseSeed}
              sourceFile={sourceFile}
              onSourceFileChange={setSourceFile}
              targetFile={targetFile}
              onTargetFileChange={setTargetFile}
            />
          )}

          {activeStep === 1 && config && (
            <RunStep
              config={config}
              run={run}
              useSeed={useSeed}
              sourceFile={sourceFile}
              targetFile={targetFile}
              onRunCreated={setRun}
            />
          )}

          {activeStep === 2 && run && (
            <LoopAStep
              run={run}
              onNewRun={(newRun, newConfig) => {
                setConfig(newConfig)
                setRun(newRun)
              }}
            />
          )}

          {activeStep === 3 && <AuditStep />}
        </Container>
      </Box>
    </Box>
  )
}

export default App
