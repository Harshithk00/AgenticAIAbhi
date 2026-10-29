import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.authStatus())
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return <AuthContext.Provider value={{ status, error, refresh }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
