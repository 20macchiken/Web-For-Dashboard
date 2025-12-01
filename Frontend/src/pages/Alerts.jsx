import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { toast } from 'react-toastify'

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Stats state
  const [stats, setStats] = useState({
    total_active: 0,
    by_severity: { low: 0, medium: 0, high: 0 }
  })

  // Filter state
  const [filters, setFilters] = useState({
    status: 'active',
    severity: 'ALL',
    category: 'ALL',
    resource_name: '',
    startDate: '',
    endDate: '',
  })

  // Pagination state
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const PAGE_SIZE = 50

  // Fetch alert stats
  const fetchStats = async () => {
    try {
      // Fetch ALL alerts (not just active)
      const { data, error: fetchError } = await supabase
        .from('alerts')
        .select('severity, status')

      if (fetchError) throw fetchError

      let activeCount = 0
      const severityCounts = { low: 0, medium: 0, high: 0 }

      data?.forEach(alert => {
        const severity = alert.severity?.toLowerCase()
        const status = alert.status?.toLowerCase()

        // Count active alerts
        if (status === 'active') {
          activeCount++
        }

        // Count ALL alerts by severity (regardless of status)
        if (severity in severityCounts) {
          severityCounts[severity]++
        }
      })

      setStats({
        total_active: activeCount,
        by_severity: severityCounts
      })
    } catch (err) {
      console.error('Error fetching stats:', err)
    }
  }

  // Fetch alerts from Supabase
  const fetchAlerts = async (reset = false) => {
    try {
      setLoading(true)
      setError('')

      const currentPage = reset ? 0 : page
      const from = currentPage * PAGE_SIZE
      const to = from + PAGE_SIZE - 1

      // Build query with filters
      let query = supabase
        .from('alerts')
        .select('*', { count: 'exact' })
        .order('triggered_at', { ascending: false })
        .range(from, to)

      // Apply filters
      if (filters.status !== 'ALL') {
        query = query.eq('status', filters.status)
      }
      if (filters.severity !== 'ALL') {
        query = query.eq('severity', filters.severity)
      }
      if (filters.category !== 'ALL') {
        query = query.eq('category', filters.category)
      }
      if (filters.resource_name) {
        query = query.ilike('resource_name', `%${filters.resource_name}%`)
      }
      if (filters.startDate) {
        query = query.gte('triggered_at', `${filters.startDate}T00:00:00`)
      }
      if (filters.endDate) {
        query = query.lte('triggered_at', `${filters.endDate}T23:59:59`)
      }

      const { data, error: fetchError } = await query

      if (fetchError) throw fetchError

      if (reset) {
        setAlerts(data || [])
        setPage(0)
      } else {
        setAlerts(prev => [...prev, ...(data || [])])
      }

      setHasMore(data && data.length === PAGE_SIZE)

    } catch (err) {
      console.error('Error fetching alerts:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Initial load
  useEffect(() => {
    fetchAlerts(true)
    fetchStats()
  }, [filters])

  // Real-time subscription
  useEffect(() => {
    const channel = supabase
      .channel('alerts_changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'alerts',
        },
        (payload) => {
          // Prepend new alert to list if it matches filters
          const newAlert = payload.new

          // Show toast notification for medium/high severity
          showAlertToast(newAlert)

          const matchesFilters =
            (filters.status === 'ALL' || newAlert.status === filters.status) &&
            (filters.severity === 'ALL' || newAlert.severity === filters.severity) &&
            (filters.category === 'ALL' || newAlert.category === filters.category) &&
            (!filters.resource_name || newAlert.resource_name?.toLowerCase().includes(filters.resource_name.toLowerCase()))

          if (matchesFilters) {
            setAlerts(prev => [newAlert, ...prev])
          }

          // Refresh stats
          fetchStats()
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'alerts',
        },
        (payload) => {
          // Update alert in list when it's modified (e.g., auto-resolved)
          const updatedAlert = payload.new

          setAlerts(prev =>
            prev.map(alert =>
              alert.id === updatedAlert.id ? updatedAlert : alert
            )
          )

          // Refresh stats when status changes
          fetchStats()
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [filters])

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleLoadMore = () => {
    setPage(prev => prev + 1)
    fetchAlerts(false)
  }

  // Show toast notification for new alert
  const showAlertToast = (alert) => {
    const severity = alert.severity?.toLowerCase()

    // Only show popup for medium and high severity
    if (severity !== 'medium' && severity !== 'high') {
      return
    }

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
    if (severity === 'high') {
      toast.error(message, {
        ...toastConfig,
        autoClose: false // High severity stays until dismissed
      })
    } else if (severity === 'medium') {
      toast.warning(message, {
        ...toastConfig,
        autoClose: 8000
      })
    }
  }

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'high':
        return '#dc3545'
      case 'medium':
        return '#ffc107'
      case 'low':
        return '#17a2b8'
      default:
        return '#6c757d'
    }
  }

  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'active':
        return '#dc3545'
      case 'acknowledged':
        return '#ffc107'
      case 'resolved':
        return '#28a745'
      case 'auto_resolved':
        return '#17a2b8'  // Blue for auto-resolved
      default:
        return '#6c757d'
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h1>System Alerts</h1>

      {/* Statistics Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 16,
        marginBottom: 20,
      }}>
        <div style={{
          backgroundColor: 'white',
          padding: 16,
          borderRadius: 8,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          borderLeft: '4px solid #dc3545',
        }}>
          <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 4 }}>Active Alerts</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#dc3545' }}>{stats.total_active}</div>
        </div>

        <div style={{
          backgroundColor: 'white',
          padding: 16,
          borderRadius: 8,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          borderLeft: '4px solid #dc3545',
        }}>
          <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 4 }}>High Severity</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#dc3545' }}>{stats.by_severity.high}</div>
        </div>

        <div style={{
          backgroundColor: 'white',
          padding: 16,
          borderRadius: 8,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          borderLeft: '4px solid #ffc107',
        }}>
          <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 4 }}>Medium Severity</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#ffc107' }}>{stats.by_severity.medium}</div>
        </div>

        <div style={{
          backgroundColor: 'white',
          padding: 16,
          borderRadius: 8,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          borderLeft: '4px solid #17a2b8',
        }}>
          <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 4 }}>Low Severity</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: '#17a2b8' }}>{stats.by_severity.low}</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 16,
        padding: 12,
        backgroundColor: '#f8f9fa',
        borderRadius: 4,
        flexWrap: 'wrap',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Status:
          </label>
          <select
            value={filters.status}
            onChange={(e) => handleFilterChange('status', e.target.value)}
            style={{ padding: '4px 8px' }}
          >
            <option value="active">Active</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
            <option value="auto_resolved">Auto-Resolved</option>
            <option value="ALL">All Status</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Severity:
          </label>
          <select
            value={filters.severity}
            onChange={(e) => handleFilterChange('severity', e.target.value)}
            style={{ padding: '4px 8px' }}
          >
            <option value="ALL">All Severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Category:
          </label>
          <select
            value={filters.category}
            onChange={(e) => handleFilterChange('category', e.target.value)}
            style={{ padding: '4px 8px' }}
          >
            <option value="ALL">All Categories</option>
            <option value="node_health">Node Health</option>
            <option value="vm_resource">VM Resource</option>
            <option value="vm_status">VM Status</option>
            <option value="application">Application</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Resource:
          </label>
          <input
            type="text"
            value={filters.resource_name}
            onChange={(e) => handleFilterChange('resource_name', e.target.value)}
            placeholder="Filter by resource..."
            style={{ padding: '4px 8px', width: 180 }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Start Date:
          </label>
          <input
            type="date"
            value={filters.startDate}
            onChange={(e) => handleFilterChange('startDate', e.target.value)}
            style={{ padding: '4px 8px' }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            End Date:
          </label>
          <input
            type="date"
            value={filters.endDate}
            onChange={(e) => handleFilterChange('endDate', e.target.value)}
            style={{ padding: '4px 8px' }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button
            onClick={() => {
              setFilters({
                status: 'active',
                severity: 'ALL',
                category: 'ALL',
                resource_name: '',
                startDate: '',
                endDate: '',
              })
            }}
            style={{
              padding: '4px 12px',
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div style={{ color: 'red', marginBottom: 12 }}>
          Error: {error}
        </div>
      )}

      {/* Alerts table */}
      {loading && alerts.length === 0 ? (
        <p>Loading alerts...</p>
      ) : alerts.length === 0 ? (
        <p>No alerts found matching the filters.</p>
      ) : (
        <>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 13,
            backgroundColor: 'white',
          }}>
            <thead>
              <tr style={{ backgroundColor: '#f8f9fa' }}>
                <th style={tableHeaderStyle}>Triggered At</th>
                <th style={tableHeaderStyle}>Severity</th>
                <th style={tableHeaderStyle}>Status</th>
                <th style={tableHeaderStyle}>Title</th>
                <th style={tableHeaderStyle}>Resource</th>
                <th style={tableHeaderStyle}>Metric</th>
                <th style={tableHeaderStyle}>Current</th>
                <th style={tableHeaderStyle}>Threshold</th>
                <th style={tableHeaderStyle}>Message</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={tableCellStyle}>
                    {formatTimestamp(alert.triggered_at)}
                  </td>
                  <td style={{ ...tableCellStyle, color: getSeverityColor(alert.severity), fontWeight: 'bold' }}>
                    {alert.severity?.toUpperCase()}
                  </td>
                  <td style={{ ...tableCellStyle, color: getStatusColor(alert.status), fontWeight: 'bold' }}>
                    {alert.status === 'auto_resolved' ? 'AUTO-RESOLVED' : alert.status?.toUpperCase()}
                  </td>
                  <td style={{ ...tableCellStyle, fontWeight: 'bold' }}>
                    {alert.title}
                  </td>
                  <td style={tableCellStyle}>
                    {alert.resource_name || '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {alert.metric_name || '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {alert.current_value != null ? `${alert.current_value.toFixed(1)}%` : '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {alert.threshold_value != null ? `${alert.threshold_value}%` : '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {alert.message ? (
                      <details>
                        <summary style={{ cursor: 'pointer', color: '#17a2b8' }}>
                          View Message
                        </summary>
                        <div style={{
                          fontSize: 12,
                          backgroundColor: '#f8f9fa',
                          padding: 8,
                          borderRadius: 4,
                          marginTop: 4,
                        }}>
                          {alert.message}
                        </div>
                      </details>
                    ) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Load more button */}
          {hasMore && (
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <button
                onClick={handleLoadMore}
                disabled={loading}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#007bff',
                  color: 'white',
                  border: 'none',
                  borderRadius: 4,
                  cursor: loading ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? 'Loading...' : 'Load More'}
              </button>
            </div>
          )}

          <div style={{
            marginTop: 16,
            fontSize: 12,
            color: '#6c757d',
            textAlign: 'center',
          }}>
            Showing {alerts.length} alerts (updates in real-time)
          </div>
        </>
      )}
    </div>
  )
}

const tableHeaderStyle = {
  padding: '8px 12px',
  textAlign: 'left',
  fontWeight: 'bold',
  borderBottom: '2px solid #dee2e6',
}

const tableCellStyle = {
  padding: '8px 12px',
  verticalAlign: 'top',
}
