import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Settings() {
  const { user } = useAuth()

  const storageKey = `dashboardURL_${user?.email}`

  const [value, setValue] = useState(
    localStorage.getItem(storageKey) || ''
  )

  const save = () => {
    if (user?.username) {
      localStorage.setItem(storageKey, value)
      alert('Saved! กลับไปหน้า Home เพื่อดูผล')
    }
  }

  const reset6h = () => {
    try {
      const url = new URL(value)
      url.searchParams.set('from', 'now-6h')
      url.searchParams.set('to', 'now')
      setValue(url.toString())
    } catch {
      alert('URL ไม่ถูกต้อง')
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Settings</h2>
      <p>ตั้งค่า/แก้ลิงก์ Grafana ที่จะใช้แสดงผล</p>

      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={{ width: '100%', height: 160, padding: 8 }}
        placeholder="https://grafana.example.com/d/abc123/my-dashboard?orgId=1&from=now-6h&to=now"
      />

      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <button onClick={save}>Save</button>
        <button onClick={reset6h}>Set time range = last 6h</button>
      </div>
    </div>
  )
}
