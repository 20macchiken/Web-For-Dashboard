import { useEffect, useState } from 'react'

export default function Home() {
  // ลองอ่านค่าจาก localStorage ก่อน ถ้าไม่มีใช้ค่าเริ่มต้น
  const [dashboardURL, setDashboardURL] = useState(
    () => localStorage.getItem('dashboardURL') ||
      'https://grafana.example.com/d/yourUid/yourSlug?orgId=1&from=now-6h&to=now'
  )

  useEffect(() => {
    localStorage.setItem('dashboardURL', dashboardURL)
  }, [dashboardURL])

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

      <div style={{ marginTop: 16, height: '80vh', border: '1px solid #ddd' }}>
        <iframe
          title="grafana-dashboard"
          src={dashboardURL}
          style={{ width: '150%', height: '150%', border: 0 }}
        />
      </div>
    </div>
  )
}
