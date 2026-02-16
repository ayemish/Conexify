import { useEffect, useRef, useState, useCallback } from 'react'

const RECONNECT_DELAYS = [2000, 5000, 15000]

/**
 * Resolve a WebSocket URL for the given API path.
 * In development (Vite on port 5173), connects directly to the backend
 * on port 8000 since Vite's HTTP proxy doesn't reliably forward WS upgrades.
 * In production, uses the current host.
 */
export function resolveWsUrl(apiPath) {
  const loc = window.location
  const port = loc.port
  // Dev mode: any non-production port (not 80, 443, or 8000) should connect
  // directly to the backend on port 8000 for WebSocket.
  const isBackend = port === '8000' || port === '80' || port === '443' || port === ''
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = isBackend ? loc.host : `${loc.hostname}:8000`
  return `${protocol}//${host}${apiPath}`
}

export function useWebSocket(url, options = {}) {
  const {
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnect = true,
    maxReconnectAttempts = 3,
  } = options

  // Store callbacks in refs so they never cause reconnect cycles
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  const onErrorRef = useRef(onError)
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  const wsRef = useRef(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimeoutRef = useRef(null)
  const mountedRef = useRef(true)
  const connectingRef = useRef(false)
  
  const [status, setStatus] = useState('disconnected')
  const [lastMessage, setLastMessage] = useState(null)
  const [error, setError] = useState(null)

  const connect = useCallback(() => {
    if (!url) return
    // Guard: don't connect if already open or in the process of connecting
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return
    if (connectingRef.current) return

    connectingRef.current = true

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = (event) => {
        connectingRef.current = false
        if (!mountedRef.current) { ws.close(); return }
        setStatus('connected')
        setError(null)
        reconnectAttemptRef.current = 0
        onOpenRef.current?.(event)
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const data = JSON.parse(event.data)
          // Auto-respond to server heartbeat pings
          if (data.type === 'ping') {
            try { ws.send(JSON.stringify({ type: 'pong' })) } catch (_) {}
            return
          }
          // Skip connected/pong housekeeping messages from triggering re-renders
          if (data.type === 'connected' || data.type === 'pong') return
          setLastMessage(data)
          onMessageRef.current?.(data, event)
        } catch (err) {
          setLastMessage(event.data)
          onMessageRef.current?.(event.data, event)
        }
      }

      ws.onclose = (event) => {
        connectingRef.current = false
        if (!mountedRef.current) return
        setStatus('disconnected')
        onCloseRef.current?.(event)

        if (reconnect && reconnectAttemptRef.current < maxReconnectAttempts) {
          const delay = RECONNECT_DELAYS[
            Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)
          ]
          setStatus('reconnecting')
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!mountedRef.current) return
            reconnectAttemptRef.current++
            connect()
          }, delay)
        } else if (reconnectAttemptRef.current >= maxReconnectAttempts) {
          setStatus('unavailable')
        }
      }

      ws.onerror = (event) => {
        connectingRef.current = false
        if (!mountedRef.current) return
        setError('WebSocket error')
        onErrorRef.current?.(event)
      }
    } catch (err) {
      connectingRef.current = false
      setError(err.message)
      setStatus('unavailable')
    }
  // connect only depends on url and reconnect settings — NOT on callbacks
  }, [url, reconnect, maxReconnectAttempts])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    connectingRef.current = false
    if (wsRef.current) {
      wsRef.current.onopen = null
      wsRef.current.onmessage = null
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('disconnected')
  }, [])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const payload = typeof data === 'string' ? data : JSON.stringify(data)
      wsRef.current.send(payload)
      return true
    }
    return false
  }, [])

  // Only reconnect when url changes — callbacks are in refs
  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [url]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    status,
    lastMessage,
    error,
    send,
    connect,
    disconnect,
    ws: wsRef.current,
  }
}

export function useDashboardWebSocket(assetId) {
  const wsUrl = assetId 
    ? resolveWsUrl(`/api/v1/ws/dashboard/${assetId}`)
    : null

  const [dashboardData, setDashboardData] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [approvals, setApprovals] = useState([])

  const handleMessage = useCallback((data) => {
    switch (data.type) {
      case 'dashboard_update':
        setDashboardData(data.dashboard)
        break
      case 'alert_update':
        setAlerts(prev => {
          const idx = prev.findIndex(a => a.alert_id === data.alert.alert_id)
          if (idx >= 0) {
            const updated = [...prev]
            updated[idx] = data.alert
            return updated
          }
          return [data.alert, ...prev]
        })
        break
      case 'alert_new':
        setAlerts(prev => [data.alert, ...prev])
        break
      case 'approval_update':
        setApprovals(prev => {
          const idx = prev.findIndex(a => a.item_id === data.item_id)
          if (idx >= 0) {
            const updated = [...prev]
            updated[idx] = { ...updated[idx], ...data.update }
            return updated
          }
          return prev
        })
        break
      case 'approval_added':
        setApprovals(prev => [data.item, ...prev])
        break
      default:
        break
    }
  }, [])

  const ws = useWebSocket(wsUrl, {
    onMessage: handleMessage,
  })

  return {
    ...ws,
    dashboardData,
    alerts,
    approvals,
  }
}

export default useWebSocket
