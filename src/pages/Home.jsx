import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Home() {
  const { user } = useAuth()

  const storageKey = `dashboardURL_${user?.username}`

  // ลองอ่านค่าจาก localStorage ก่อน ถ้าไม่มีใช้ค่าเริ่มต้น
  const [dashboardURL, setDashboardURL] = useState(
    () => localStorage.getItem(storageKey) ||
      'https://grafana.example.com/d/yourUid/yourSlug?orgId=1&from=now-6h&to=now'
  )

  useEffect(() => {
    if (user?.username) {
      localStorage.setItem(storageKey, dashboardURL)
    }
  }, [dashboardURL, storageKey, user?.username])

  const normalizeURL = (url) => {
    if (!url || url.trim() === '') return ''
    const trimmedUrl = url.trim()
    if (!/^https?:\/\//i.test(trimmedUrl)) {
      return `https://${trimmedUrl}`
    }
    return trimmedUrl
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>URL Viewer</h2>

      <label style={{ display: 'block', marginBottom: 8 }}>
        Dashboard URL (วางลิงก์จากปุ่ม Share ของ Grafana)
      </label>
      <input
        value={dashboardURL}
        onChange={(e) => setDashboardURL(e.target.value)}
        style={{ width: '100%', padding: 8 }}
        placeholder="https://grafana.example.com/d/abc123/my-dashboard?orgId=1&from=now-6h&to=now"
      />

      <div style={{
        marginTop: 16,
        height: '80vh',
        border: '1px solid #ddd',
        overflow: 'hidden',
        position: 'relative'
      }}>
        <iframe
          title="grafana-dashboard"
          src={normalizeURL(dashboardURL)}
          style={{
            width: '100%',
            height: '100%',
            border: 0,
            transform: 'scale(1)',
            transformOrigin: 'top left'
          }}
        />
      </div>
    </div>
  )
}
