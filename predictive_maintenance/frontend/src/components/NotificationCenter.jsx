/**
 * Notification Center
 *
 * Unified notification drawer that aggregates alerts, KPI changes,
 * approval updates, and work order status from all modules.
 */

import { useState } from 'react'
import {
  Bell, X, Check, CheckCheck, AlertTriangle, BarChart3,
  ClipboardList, Shield, Trash2, Activity
} from 'lucide-react'
import { useAppContext } from '../context/AppContext'

const TYPE_CONFIG = {
  alert:      { icon: AlertTriangle, color: '#ef4444', bg: '#fef2f2', label: 'Alert' },
  kpi:        { icon: BarChart3,     color: '#2563eb', bg: '#eff6ff', label: 'KPI' },
  approval:   { icon: Shield,        color: '#8b5cf6', bg: '#f5f3ff', label: 'Approval' },
  workorder:  { icon: ClipboardList, color: '#f59e0b', bg: '#fffbeb', label: 'Work Order' },
  system:     { icon: Activity,      color: '#64748b', bg: '#f8fafc', label: 'System' },
}

function NotificationItem({ notification, onMarkRead }) {
  const cfg = TYPE_CONFIG[notification.type] || TYPE_CONFIG.system
  const Icon = cfg.icon
  const age = getRelativeTime(notification.timestamp)

  return (
    <div
      style={{
        display: 'flex', gap: '0.65rem', padding: '0.65rem 0.85rem',
        background: notification.read ? '#fff' : cfg.bg,
        borderLeft: `3px solid ${notification.read ? '#e2e8f0' : cfg.color}`,
        borderBottom: '1px solid #f1f5f9',
        cursor: notification.read ? 'default' : 'pointer',
        transition: 'background 0.15s',
      }}
      onClick={() => !notification.read && onMarkRead(notification.id)}
    >
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: `${cfg.color}15`, color: cfg.color,
      }}>
        <Icon size={14} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: '0.82rem', fontWeight: notification.read ? 400 : 600,
          color: '#1e293b', lineHeight: 1.4,
        }}>
          {notification.title || notification.message}
        </div>
        {notification.detail && (
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 2, lineHeight: 1.35 }}>
            {notification.detail}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 3 }}>
          <span style={{
            fontSize: '0.65rem', padding: '1px 6px', borderRadius: 4,
            background: cfg.color, color: '#fff', fontWeight: 600,
          }}>
            {cfg.label}
          </span>
          <span style={{ fontSize: '0.68rem', color: '#94a3b8' }}>{age}</span>
        </div>
      </div>
      {!notification.read && (
        <div style={{
          width: 8, height: 8, borderRadius: '50%', background: cfg.color,
          flexShrink: 0, marginTop: 6,
        }} />
      )}
    </div>
  )
}

function getRelativeTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function NotificationCenter() {
  const {
    notifications, unreadCount, markNotificationRead, markAllRead, clearNotifications,
  } = useAppContext()
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('all')

  const filtered = filter === 'all'
    ? notifications
    : filter === 'unread'
      ? notifications.filter(n => !n.read)
      : notifications.filter(n => n.type === filter)

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          position: 'relative', background: 'none', border: 'none',
          cursor: 'pointer', padding: '0.35rem', color: '#94a3b8',
        }}
        title="Notifications"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: 0, right: 0,
            width: 18, height: 18, borderRadius: '50%',
            background: '#ef4444', color: '#fff', fontSize: '0.6rem',
            fontWeight: 700, display: 'flex', alignItems: 'center',
            justifyContent: 'center', border: '2px solid #1e293b',
          }}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', right: 0, zIndex: 1000,
          width: 380, maxHeight: '70vh', background: '#fff',
          borderRadius: 12, boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
          border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column',
        }}>
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0.75rem 1rem', borderBottom: '1px solid #e2e8f0',
          }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#1e293b' }}>
              Notifications {unreadCount > 0 && `(${unreadCount})`}
            </h3>
            <div style={{ display: 'flex', gap: 4 }}>
              <button onClick={markAllRead} title="Mark all read" style={{
                border: 'none', background: '#f1f5f9', borderRadius: 6,
                padding: '4px 8px', cursor: 'pointer', color: '#64748b',
                display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.7rem',
              }}>
                <CheckCheck size={12} /> Read all
              </button>
              <button onClick={clearNotifications} title="Clear all" style={{
                border: 'none', background: '#f1f5f9', borderRadius: 6,
                padding: '4px 8px', cursor: 'pointer', color: '#64748b',
                display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.7rem',
              }}>
                <Trash2 size={12} />
              </button>
              <button onClick={() => setOpen(false)} style={{
                border: 'none', background: 'none', cursor: 'pointer',
                color: '#94a3b8', padding: '4px',
              }}>
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Filter tabs */}
          <div style={{
            display: 'flex', gap: 4, padding: '0.5rem 0.75rem',
            borderBottom: '1px solid #f1f5f9', flexWrap: 'wrap',
          }}>
            {[
              { id: 'all', label: 'All' },
              { id: 'unread', label: 'Unread' },
              { id: 'alert', label: 'Alerts' },
              { id: 'kpi', label: 'KPI' },
              { id: 'approval', label: 'Approvals' },
              { id: 'workorder', label: 'Work Orders' },
            ].map(f => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                style={{
                  padding: '2px 8px', borderRadius: 6, border: 'none',
                  fontSize: '0.7rem', fontWeight: 600, cursor: 'pointer',
                  background: filter === f.id ? '#1e293b' : '#f1f5f9',
                  color: filter === f.id ? '#fff' : '#64748b',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* List */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filtered.length === 0 ? (
              <div style={{
                padding: '2rem', textAlign: 'center', color: '#94a3b8',
                fontSize: '0.85rem',
              }}>
                <Bell size={32} style={{ margin: '0 auto 0.5rem', opacity: 0.3 }} />
                <p style={{ margin: 0 }}>No notifications</p>
              </div>
            ) : (
              filtered.map(n => (
                <NotificationItem
                  key={n.id}
                  notification={n}
                  onMarkRead={markNotificationRead}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
