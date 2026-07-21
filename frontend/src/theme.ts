import { createTheme } from '@mui/material/styles'

// Design system reference (brief §14): warm off-white canvas, white cards,
// hairline borders, one accent (bottle green), green/amber/red reserved
// strictly for status. Schibsted Grotesk for UI, Spline Sans Mono for every
// numeric figure (amounts, %, versions, timestamps) — see the .figure class
// used throughout instead of the default body font.

const bottleGreen = '#1F4B3F'
const canvas = '#F7F4EE'
const hairline = 'rgba(31, 40, 36, 0.14)'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: bottleGreen, contrastText: '#FFFFFF' },
    background: { default: canvas, paper: '#FFFFFF' },
    success: { main: '#2E7D46' },
    warning: { main: '#B4790A' },
    error: { main: '#B3261E' },
    divider: hairline,
    text: { primary: '#1B211D', secondary: '#5B6560' },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: '"Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif',
    h1: { fontWeight: 700 },
    h2: { fontWeight: 700 },
    h3: { fontWeight: 600 },
    h4: { fontWeight: 600 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${hairline}`,
        },
        elevation1: { boxShadow: 'none' },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: `1px solid ${hairline}`,
          boxShadow: 'none',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 6 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderBottom: `1px solid ${hairline}` },
      },
    },
  },
})

export const FIGURE_FONT = '"Spline Sans Mono", ui-monospace, monospace'

export const statusColor = {
  draft: '#B4790A',
  approved: '#2E7D46',
  open: '#5B6560',
  auto_accepted: '#2E7D46',
  routed_to_human: '#B4790A',
  resolved: '#1F4B3F',
} as const

export const severityColor = {
  low: '#2E7D46',
  medium: '#B4790A',
  high: '#B3261E',
} as const
