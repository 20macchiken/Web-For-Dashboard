import { createContext, useContext, useState, useEffect } from 'react'
import { useAuth } from './AuthContext'
import { supabase } from '../lib/supabaseClient'
import { toast } from 'react-toastify'

const AlertContext = createContext()

export const useAlerts = () => {
  const context = useContext(AlertContext)
  if (!context) {
    throw new Error('useAlerts must be used within AlertProvider')
  }
  return context
}

export const AlertProvider = ({ children }) => {
  const { user } = useAuth()
  const [alerts, setAlerts] = useState([])
  const [alertStats, setAlertStats] = useState({
    total_active: 0,
    total_acknowledged: 0,
    total_resolved: 0,
    by_severity: { low: 0, medium: 0, high: 0 }
  })
  const [loading, setLoading] = useState(false)

  // Fetch alert statistics
  const fetchAlertStats = async () => {
    if (!user) return

    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/alerts/stats/summary`, {
        headers: {
          'Authorization': `Bearer ${user.access_token}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setAlertStats(data)
      }
    } catch (error) {
      console.error('Error fetching alert stats:', error)
    }
  }

  // Fetch alerts list
  const fetchAlerts = async (status = 'active', severity = null) => {
    if (!user) return

    setLoading(true)
    try {
      let url = `${import.meta.env.VITE_API_BASE_URL}/api/alerts?status=${status}&limit=50`
      if (severity) {
        url += `&severity=${severity}`
      }

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${user.access_token}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setAlerts(data.alerts || [])
      }
    } catch (error) {
      console.error('Error fetching alerts:', error)
      toast.error('Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }

  // Acknowledge an alert
  const acknowledgeAlert = async (alertId) => {
    if (!user) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL}/api/alerts/${alertId}/acknowledge`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${user.access_token}`
          }
        }
      )

      if (response.ok) {
        toast.success('Alert acknowledged')
        // Refetch with current filter (default to 'active')
        await fetchAlerts('active')
        await fetchAlertStats()
        return true
      } else {
        const errorData = await response.json().catch(() => ({}))
        console.error('Acknowledge failed:', response.status, errorData)
        toast.error(`Failed to acknowledge alert: ${errorData.error || response.statusText}`)
        return false
      }
    } catch (error) {
      console.error('Error acknowledging alert:', error)
      toast.error('Failed to acknowledge alert')
      return false
    }
  }

  // Resolve an alert
  const resolveAlert = async (alertId) => {
    if (!user) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL}/api/alerts/${alertId}/resolve`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${user.access_token}`
          }
        }
      )

      if (response.ok) {
        toast.success('Alert resolved')
        // Refetch with current filter (default to 'active')
        await fetchAlerts('active')
        await fetchAlertStats()
        return true
      } else {
        const errorData = await response.json().catch(() => ({}))
        console.error('Resolve failed:', response.status, errorData)
        toast.error(`Failed to resolve alert: ${errorData.error || response.statusText}`)
        return false
      }
    } catch (error) {
      console.error('Error resolving alert:', error)
      toast.error('Failed to resolve alert')
      return false
    }
  }

  // Show toast notification for new alert
  const showAlertToast = (alert) => {
    const toastConfig = {
      position: 'top-right',
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true
    }

    const message = (
      <div>
        <strong>{alert.title}</strong>
        <div style={{ fontSize: '0.9em', marginTop: '4px' }}>
          {alert.message}
        </div>
        <div style={{ fontSize: '0.8em', marginTop: '4px', opacity: 0.8 }}>
          {alert.resource_name} - {alert.metric_name}: {alert.current_value?.toFixed(1)}%
        </div>
      </div>
    )

    // Different toast styles based on severity
    if (alert.severity === 'high') {
      toast.error(message, {
        ...toastConfig,
        autoClose: false // High severity stays until dismissed
      })
    } else if (alert.severity === 'medium') {
      toast.warning(message, {
        ...toastConfig,
        autoClose: 8000
      })
    } else {
      toast.info(message, {
        ...toastConfig,
        autoClose: 5000
      })
    }
  }

  // Subscribe to real-time alerts
  useEffect(() => {
    if (!user) return

    // Initial fetch
    fetchAlerts()
    fetchAlertStats()

    // Subscribe to new alerts
    const channel = supabase
      .channel('alerts_channel')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'alerts'
        },
        (payload) => {
          console.log('New alert received:', payload.new)
          const newAlert = payload.new

          // Show toast notification
          showAlertToast(newAlert)

          // Add to alerts list if viewing active alerts
          setAlerts(prev => [newAlert, ...prev])

          // Update stats
          fetchAlertStats()
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'alerts'
        },
        (payload) => {
          console.log('Alert updated:', payload.new)

          // Update alert in list
          setAlerts(prev =>
            prev.map(alert =>
              alert.id === payload.new.id ? payload.new : alert
            )
          )

          // Update stats
          fetchAlertStats()
        }
      )
      .subscribe()

    // Cleanup subscription on unmount
    return () => {
      supabase.removeChannel(channel)
    }
  }, [user])

  const value = {
    alerts,
    alertStats,
    loading,
    fetchAlerts,
    fetchAlertStats,
    acknowledgeAlert,
    resolveAlert
  }

  return (
    <AlertContext.Provider value={value}>
      {children}
    </AlertContext.Provider>
  )
}
