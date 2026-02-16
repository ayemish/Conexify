/**
 * Global Application Context
 *
 * Provides shared state across all components:
 * - siteId: current site/tenant
 * - user: authenticated user info
 * - activeAssetId: currently selected asset
 * - notifications: unified notification queue
 * - auth token management
 */

import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'

const AppContext = createContext(null)

const AUTH_TOKEN_KEY = 'pdm_auth_token'
const SITE_ID_KEY = 'pdm_site_id'

export function AppProvider({ children }) {
  // ── Site / Tenant ───────────────────────────────────────────────
  const [siteId, setSiteIdState] = useState(
    () => localStorage.getItem(SITE_ID_KEY) || 'default'
  )
  const setSiteId = useCallback((id) => {
    setSiteIdState(id)
    localStorage.setItem(SITE_ID_KEY, id)
  }, [])

  // ── Auth ────────────────────────────────────────────────────────
  const [user, setUser] = useState(null)
  const [authToken, setAuthTokenState] = useState(
    () => localStorage.getItem(AUTH_TOKEN_KEY) || null
  )
  const setAuthToken = useCallback((token) => {
    setAuthTokenState(token)
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token)
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY)
    }
  }, [])

  const login = useCallback((token, userInfo) => {
    setAuthToken(token)
    setUser(userInfo)
  }, [setAuthToken])

  const logout = useCallback(() => {
    setAuthToken(null)
    setUser(null)
  }, [setAuthToken])

  // ── Active Asset ────────────────────────────────────────────────
  const [activeAssetId, setActiveAssetId] = useState(null)

  // ── Notifications ───────────────────────────────────────────────
  const [notifications, setNotifications] = useState([])
  const notifIdRef = useRef(0)

  const addNotification = useCallback((notification) => {
    const id = ++notifIdRef.current
    const entry = {
      id,
      timestamp: new Date().toISOString(),
      read: false,
      ...notification,
    }
    setNotifications(prev => [entry, ...prev].slice(0, 200))
    return id
  }, [])

  const markNotificationRead = useCallback((id) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
  }, [])

  const clearNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  const unreadCount = notifications.filter(n => !n.read).length

  // ── Available Sites (for multi-site selector) ───────────────────
  const [availableSites, setAvailableSites] = useState([
    { id: 'default', name: 'Default Site', address: '' },
  ])

  // Fetch available sites on mount
  useEffect(() => {
    async function fetchSites() {
      try {
        const res = await fetch('/api/v1/fleet/sites')
        if (res.ok) {
          const data = await res.json()
          if (data.sites && data.sites.length > 0) {
            setAvailableSites(data.sites)
          }
        }
      } catch {
        // Silently use defaults
      }
    }
    fetchSites()
  }, [])

  const value = {
    // Site
    siteId,
    setSiteId,
    availableSites,
    setAvailableSites,
    // Auth
    user,
    authToken,
    login,
    logout,
    isAuthenticated: !!authToken,
    // Asset
    activeAssetId,
    setActiveAssetId,
    // Notifications
    notifications,
    unreadCount,
    addNotification,
    markNotificationRead,
    markAllRead,
    clearNotifications,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useAppContext() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppContext must be used within AppProvider')
  return ctx
}

export default AppContext
