import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../context/AuthContext'

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filter state
  const [filters, setFilters] = useState({
    level: 'ALL',
    category: 'ALL',
    action: '',
    user_email: '',
    startDate: '',
    endDate: '',
  })

  // Pagination state
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const PAGE_SIZE = 50

  // Unified export state
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportStartDate, setExportStartDate] = useState('')
  const [exportEndDate, setExportEndDate] = useState('')

  const { session } = useAuth()
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000'

  // Fetch logs from Supabase
  const fetchLogs = async (reset = false) => {
    try {
      setLoading(true)
      setError('')

      const currentPage = reset ? 0 : page
      const from = currentPage * PAGE_SIZE
      const to = from + PAGE_SIZE - 1

      // Build query with filters
      let query = supabase
        .from('system_logs')
        .select('*', { count: 'exact' })
        .order('created_at', { ascending: false })
        .range(from, to)

      // Apply filters
      if (filters.level !== 'ALL') {
        query = query.eq('level', filters.level)
      }
      if (filters.category !== 'ALL') {
        query = query.eq('category', filters.category)
      }
      if (filters.action) {
        query = query.ilike('action', `%${filters.action}%`)
      }
      if (filters.user_email) {
        query = query.ilike('user_email', `%${filters.user_email}%`)
      }
      if (filters.startDate) {
        query = query.gte('created_at', `${filters.startDate}T00:00:00`)
      }
      if (filters.endDate) {
        query = query.lte('created_at', `${filters.endDate}T23:59:59`)
      }

      const { data, error: fetchError } = await query

      if (fetchError) throw fetchError

      if (reset) {
        setLogs(data || [])
        setPage(0)
      } else {
        setLogs(prev => [...prev, ...(data || [])])
      }

      setHasMore(data && data.length === PAGE_SIZE)

    } catch (err) {
      console.error('Error fetching logs:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Initial load
  useEffect(() => {
    fetchLogs(true)
  }, [filters])

  // Real-time subscription
  useEffect(() => {
    const channel = supabase
      .channel('system_logs_changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'system_logs',
        },
        (payload) => {
          // Prepend new log to list if it matches filters
          const newLog = payload.new
          const matchesFilters =
            (filters.level === 'ALL' || newLog.level === filters.level) &&
            (filters.category === 'ALL' || newLog.category === filters.category) &&
            (!filters.action || newLog.action?.toLowerCase().includes(filters.action.toLowerCase())) &&
            (!filters.user_email || newLog.user_email?.includes(filters.user_email))

          if (matchesFilters) {
            setLogs(prev => [newLog, ...prev])
          }
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [filters])

  // Click-outside handler for export menu
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (showExportMenu && !event.target.closest('[data-export-menu]')) {
        setShowExportMenu(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showExportMenu])

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleLoadMore = () => {
    setPage(prev => prev + 1)
    fetchLogs(false)
  }

  const handleUnifiedExport = async (exportType) => {
    try {
      setExporting(true)
      setShowExportMenu(false)
      setError('')

      // Determine what to include based on export type
      let includeInfra = false
      let includeMetrics = false
      let format = 'json'
      let multiFormat = false

      // Parse export type: "metrics-csv", "metrics-json", "metrics-lineprotocol", "combined-csv-inline", "combined-json-inline"
      if (exportType.startsWith('metrics-')) {
        includeMetrics = true
        format = exportType.replace('metrics-', '')
      } else if (exportType === 'combined-csv-inline') {
        includeMetrics = true
        format = 'csv'
        multiFormat = true
      } else if (exportType === 'combined-json-inline') {
        includeMetrics = true
        format = 'json'
        multiFormat = true
      }

      // Validate date range if metrics are included
      if (includeMetrics && (!exportStartDate || !exportEndDate)) {
        setError('Please select both start and end dates for metrics export')
        setExporting(false)
        return
      }

      if (includeMetrics) {
        const startDate = new Date(exportStartDate)
        const endDate = new Date(exportEndDate)
        if (startDate >= endDate) {
          setError('Start date must be before end date')
          setExporting(false)
          return
        }
      }

      // Get auth token
      const token = session?.access_token
      if (!token) {
        throw new Error('No authentication token available')
      }

      // Build URL
      let url = `${API_BASE_URL}/api/export/unified?format=${format}&include_infrastructure=${includeInfra}&include_metrics=${includeMetrics}&multi_format=${multiFormat}`

      if (includeMetrics) {
        const startISO = new Date(exportStartDate).toISOString()
        const endISO = new Date(exportEndDate).toISOString()
        url += `&start_time=${encodeURIComponent(startISO)}&end_time=${encodeURIComponent(endISO)}`
      }

      // Fetch export data
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Authentication failed - please log in again')
        }
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.error || `Export failed with status ${response.status}`)
      }

      // Get filename from Content-Disposition header or generate one
      const contentDisposition = response.headers.get('Content-Disposition')
      let fileExt = format === 'lineprotocol' ? 'txt' : format
      if (multiFormat) {
        fileExt = 'zip'
      }
      let filename = `export_${new Date().toISOString().replace(/[:.]/g, '-')}.${fileExt}`

      if (contentDisposition) {
        const matches = contentDisposition.match(/filename="?([^"]+)"?/)
        if (matches && matches[1]) {
          filename = matches[1]
        }
      }

      // Convert response to blob and trigger download
      const blob = await response.blob()
      const url2 = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url2
      a.download = filename
      document.body.appendChild(a)
      a.click()

      // Cleanup
      window.URL.revokeObjectURL(url2)
      document.body.removeChild(a)

    } catch (err) {
      console.error('Export error:', err)
      setError(err.message || 'Failed to export data')
    } finally {
      setExporting(false)
    }
  }

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString('th-TH', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getLevelColor = (level) => {
    switch (level) {
      case 'ERROR':
      case 'CRITICAL':
        return '#dc3545'
      case 'WARNING':
        return '#ffc107'
      case 'INFO':
        return '#17a2b8'
      case 'DEBUG':
        return '#6c757d'
      default:
        return '#000'
    }
  }

  // Style helpers for unified export menu
  const menuItemStyle = {
    width: '100%',
    padding: '8px 12px',
    border: 'none',
    background: 'none',
    textAlign: 'left',
    cursor: 'pointer',
    fontSize: 13,
    borderBottom: '1px solid #dee2e6'
  }

  const handleMouseEnter = (e) => e.target.style.backgroundColor = '#f8f9fa'
  const handleMouseLeave = (e) => e.target.style.backgroundColor = 'transparent'

  return (
    <div style={{ padding: 16 }}>
      <h1>System Logs</h1>

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
            Level:
          </label>
          <select
            value={filters.level}
            onChange={(e) => handleFilterChange('level', e.target.value)}
            style={{ padding: '4px 8px' }}
          >
            <option value="ALL">All Levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
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
            <option value="vm_operation">VM Operation</option>
            <option value="api_request">API Request</option>
            <option value="auth_event">Auth Event</option>
            <option value="system_error">System Error</option>
            <option value="system">System</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Action:
          </label>
          <input
            type="text"
            value={filters.action}
            onChange={(e) => handleFilterChange('action', e.target.value)}
            placeholder="e.g. vm_start, list_vms..."
            style={{ padding: '4px 8px', width: 180 }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            User Email:
          </label>
          <input
            type="text"
            value={filters.user_email}
            onChange={(e) => handleFilterChange('user_email', e.target.value)}
            placeholder="Filter by email..."
            style={{ padding: '4px 8px', width: 200 }}
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
                level: 'ALL',
                category: 'ALL',
                action: '',
                user_email: '',
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

        {/* Unified Export Section */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, position: 'relative' }} data-export-menu>
          {/* Date pickers - always visible */}
          <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                Start Date (for metrics):
              </label>
              <input
                type="datetime-local"
                value={exportStartDate}
                onChange={(e) => setExportStartDate(e.target.value)}
                style={{ padding: '4px 8px', fontSize: 12 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                End Date (for metrics):
              </label>
              <input
                type="datetime-local"
                value={exportEndDate}
                onChange={(e) => setExportEndDate(e.target.value)}
                style={{ padding: '4px 8px', fontSize: 12 }}
              />
            </div>
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={exporting}
              style={{
                padding: '4px 12px',
                backgroundColor: exporting ? '#6c757d' : '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: exporting ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                whiteSpace: 'nowrap'
              }}
            >
              {exporting ? 'Exporting...' : 'Export Data'}
              <span style={{ fontSize: 10 }}>▼</span>
            </button>
          </div>

          {/* Unified dropdown menu */}
          {showExportMenu && !exporting && (
            <div style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 4,
              backgroundColor: 'white',
              border: '1px solid #dee2e6',
              borderRadius: 4,
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              zIndex: 1000,
              minWidth: 220
            }}>
              {/* Metrics Only */}
              <div style={{ padding: '4px 8px', fontSize: 11, fontWeight: 'bold', color: '#6c757d', borderBottom: '1px solid #dee2e6' }}>Metrics Only</div>
              <button onClick={() => handleUnifiedExport('metrics-csv')} style={menuItemStyle} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>CSV</button>
              <button onClick={() => handleUnifiedExport('metrics-json')} style={menuItemStyle} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>JSON</button>
              <button onClick={() => handleUnifiedExport('metrics-lineprotocol')} style={{...menuItemStyle, borderBottom: '2px solid #dee2e6'}} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>Line Protocol (DB Format)</button>

              {/* Combined */}
              <div style={{ padding: '4px 8px', fontSize: 11, fontWeight: 'bold', color: '#6c757d', borderBottom: '1px solid #dee2e6' }}>Combined</div>
              <button onClick={() => handleUnifiedExport('combined-csv-inline')} style={menuItemStyle} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>Metrics (CSV + Inline)</button>
              <button onClick={() => handleUnifiedExport('combined-json-inline')} style={menuItemStyle} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>Metrics (JSON + Inline)</button>
            </div>
          )}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div style={{ color: 'red', marginBottom: 12 }}>
          Error: {error}
        </div>
      )}

      {/* Logs table */}
      {loading && logs.length === 0 ? (
        <p>Loading logs...</p>
      ) : logs.length === 0 ? (
        <p>No logs found matching the filters.</p>
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
                <th style={tableHeaderStyle}>Time</th>
                <th style={tableHeaderStyle}>Level</th>
                <th style={tableHeaderStyle}>Category</th>
                <th style={tableHeaderStyle}>Action</th>
                <th style={tableHeaderStyle}>User</th>
                <th style={tableHeaderStyle}>Endpoint</th>
                <th style={tableHeaderStyle}>Status</th>
                <th style={tableHeaderStyle}>Duration</th>
                <th style={tableHeaderStyle}>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={tableCellStyle}>
                    {formatTimestamp(log.created_at)}
                  </td>
                  <td style={{ ...tableCellStyle, color: getLevelColor(log.level), fontWeight: 'bold' }}>
                    {log.level}
                  </td>
                  <td style={tableCellStyle}>{log.category}</td>
                  <td style={tableCellStyle}>{log.action}</td>
                  <td style={tableCellStyle}>{log.user_email || '-'}</td>
                  <td style={{ ...tableCellStyle, fontSize: 11, fontFamily: 'monospace' }}>
                    {log.endpoint ? (
                      <>
                        <span style={{ color: '#6c757d' }}>{log.http_method}</span>{' '}
                        {log.endpoint}
                      </>
                    ) : '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {log.status_code ? (
                      <span style={{
                        color: log.status_code < 400 ? '#28a745' : '#dc3545',
                        fontWeight: 'bold',
                      }}>
                        {log.status_code}
                      </span>
                    ) : '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {log.duration_ms ? `${log.duration_ms}ms` : '-'}
                  </td>
                  <td style={tableCellStyle}>
                    {log.error_message ? (
                      <details>
                        <summary style={{ cursor: 'pointer', color: '#dc3545' }}>
                          Error
                        </summary>
                        <pre style={{
                          fontSize: 11,
                          backgroundColor: '#f8f9fa',
                          padding: 8,
                          borderRadius: 4,
                          overflow: 'auto',
                          marginTop: 4,
                        }}>
                          {log.error_message}
                        </pre>
                      </details>
                    ) : log.metadata && Object.keys(log.metadata).length > 0 ? (
                      <details>
                        <summary style={{ cursor: 'pointer', color: '#17a2b8' }}>
                          Metadata
                        </summary>
                        <pre style={{
                          fontSize: 11,
                          backgroundColor: '#f8f9fa',
                          padding: 8,
                          borderRadius: 4,
                          overflow: 'auto',
                          marginTop: 4,
                        }}>
                          {JSON.stringify(log.metadata, null, 2)}
                        </pre>
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
            Showing {logs.length} logs (updates in real-time)
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
