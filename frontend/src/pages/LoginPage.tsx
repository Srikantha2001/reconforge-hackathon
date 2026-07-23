import { useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Stack, TextField, Typography } from '@mui/material'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../api'

const DEMO_CREDENTIALS = [
  { label: 'Maker', email: 'maker@db.com', password: 'maker123' },
  { label: 'Checker', email: 'checker@db.com', password: 'checker123' },
  { label: 'Client', email: 'client@alphacapital.com', password: 'client123' },
]

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const fill = (creds: { email: string; password: string }) => {
    setEmail(creds.email)
    setPassword(creds.password)
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 420 }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: '-0.02em' }}>
            ReconOS
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Deutsche Bank Securities Services
          </Typography>

          <form onSubmit={submit}>
            <Stack spacing={2}>
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                fullWidth
                autoFocus
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                fullWidth
              />
              {error && <Alert severity="error">{error}</Alert>}
              <Button type="submit" variant="contained" disabled={loading || !email || !password}>
                {loading ? 'Signing in…' : 'Sign in'}
              </Button>
            </Stack>
          </form>

          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 3, mb: 1 }}>
            Demo accounts — click to fill:
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
            {DEMO_CREDENTIALS.map((c) => (
              <Button key={c.email} size="small" variant="outlined" onClick={() => fill(c)}>
                {c.label}
              </Button>
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}
