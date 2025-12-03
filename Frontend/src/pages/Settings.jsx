import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Settings() {
  const { user } = useAuth()

  // Per-user key; if user not ready yet, no key
  const storageKey = user?.email ? `dashboardURL_${user.email}` : null

  const [value, setValue] = useState('')
  const [message, setMessage] = useState(null)

  // Load from localStorage whenever user (and thus storageKey) changes
  useEffect(() => {
    if (!storageKey) return
    const saved = localStorage.getItem(storageKey)
    setValue(saved || '')
  }, [storageKey])

  const save = () => {
    setMessage(null)

    if (!storageKey) {
      setMessage('ยังไม่ได้เข้าสู่ระบบ เลยบันทึก URL ไม่ได้ครับ')
      return
    }

    const trimmed = (value || '').trim()

    if (!trimmed) {
      // Empty = clear URL
      localStorage.removeItem(storageKey)
      setMessage('ลบ Dashboard URL เรียบร้อยแล้ว (หน้า Home จะไม่แสดงกราฟานา)')
      return
    }

    // Ensure it has http/https in front
    const normalized =
      /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`

    localStorage.setItem(storageKey, normalized)
    setValue(normalized)
    setMessage('Saved! กลับไปหน้า Home เพื่อดูผล')
  }

  const reset6h = () => {
    if (!value) {
      alert('ยังไม่มี URL ให้ปรับช่วงเวลา')
      return
    }

    try {
      const url = new URL(value)
      url.searchParams.set('from', 'now-6h')
      url.searchParams.set('to', 'now')
      const updated = url.toString()
      setValue(updated)

      if (storageKey) {
        localStorage.setItem(storageKey, updated)
      }
    } catch {
      alert('URL ไม่ถูกต้อง')
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Settings</h2>
      <p>ตั้งค่า/แก้ลิงก์ Grafana ที่จะใช้แสดงผลบนหน้า Home</p>
      <p style={{ fontSize: 13, color: '#ccc' }}>
        แนะนำ: ใช้ลิงก์แบบ <strong>Public dashboard</strong> จากปุ่ม Share
        ใน Grafana แล้วค่อยวางที่นี่
      </p>

      <textarea
        value={value}
        onChange={(e) => {
          setMessage(null)
          setValue(e.target.value)
        }}
        style={{ width: '100%', height: 160, padding: 8 }}
        placeholder="https://your-grafana-host/public-dashboards/...."
      />

      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <button onClick={save}>Save</button>
        <button onClick={reset6h}>Set time range = last 6h</button>
      </div>

      {message && (
        <div style={{ marginTop: 8, fontSize: 13, color: '#4caf50' }}>
          {message}
        </div>
      )}
    </div>
  )
}
