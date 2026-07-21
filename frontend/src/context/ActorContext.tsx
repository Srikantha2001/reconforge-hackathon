import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api'
import type { Actor } from '../types'

interface ActorContextValue {
  actors: Actor[]
  actingAs: string
  setActingAs: (id: string) => void
  actingActor: Actor | undefined
}

const ActorContext = createContext<ActorContextValue | undefined>(undefined)

// The maker-checker mechanism without auth (§11 G1): the user picks who
// they're "acting as". No login, no passwords — the approval gate enforces
// approver_id != author_id server-side; this just drives the UI selector.
export function ActorProvider({ children }: { children: ReactNode }) {
  const [actors, setActors] = useState<Actor[]>([])
  const [actingAs, setActingAsState] = useState<string>(
    () => localStorage.getItem('reconforge.actingAs') || '',
  )

  useEffect(() => {
    api.actors().then((list) => {
      setActors(list)
      if (!actingAs && list.length > 0) {
        setActingAsState(list[0].id)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setActingAs = (id: string) => {
    setActingAsState(id)
    localStorage.setItem('reconforge.actingAs', id)
  }

  const value = useMemo(
    () => ({ actors, actingAs, setActingAs, actingActor: actors.find((a) => a.id === actingAs) }),
    [actors, actingAs],
  )

  return <ActorContext.Provider value={value}>{children}</ActorContext.Provider>
}

export function useActor() {
  const ctx = useContext(ActorContext)
  if (!ctx) throw new Error('useActor must be used within ActorProvider')
  return ctx
}
