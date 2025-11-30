// src/pages/Home.jsx
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { supabase } from '../lib/supabaseClient'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000'

export default function Home() {
  const { user } = useAuth()

  // ---------- ROLE PART ----------
  // Role in Users table: 1 = student, 2 = staff/admin/other
  const [role, setRole] = useState(null)
  const [roleError, setRoleError] = useState('')

  useEffect(() => {
    if (!user?.id) return

    let cancelled = false

    async function fetchRole() {
      try {
        setRoleError('')

        const { data, error } = await supabase
          .from('Users')
          .select('Role')
          .eq('id', user.id)
          .single()

        if (cancelled) return

        if (error) {
          console.log('Fetch role error:', error)

          // PGRST116 = "No rows in result" -> row not created yet
          if (error.code === 'PGRST116') {
            setRole(null)
            setRoleError('')
            return
          }

          // Real error (permissions, etc.)
          setRoleError('ไม่สามารถโหลดข้อมูลสิทธิ์ผู้ใช้ได้')
          return
        }

        setRole(data?.Role ?? null)
      } catch (err) {
        if (cancelled) return
        console.error(err)
        setRoleError('ไม่สามารถโหลดข้อมูลสิทธิ์ผู้ใช้ได้')
      }
    }

    fetchRole()

    return () => {
      cancelled = true
    }
  }, [user])

  // ---------- GRAFANA URL PART ----------
  const storageKey = `dashboardURL_${user?.email}`

  const [dashboardURL, setDashboardURL] = useState(
    () =>
      localStorage.getItem(storageKey) ||
      'https://grafana.example.com/d/yourUid/yourSlug?orgId=1&from=now-6h&to=now'
  )

  useEffect(() => {
    if (user?.email) {
      localStorage.setItem(storageKey, dashboardURL)
    }
  }, [dashboardURL, storageKey, user?.email])

  const normalizeURL = (url) => {
    if (!url || url.trim() === '') return ''
    const trimmedUrl = url.trim()
    if (!/^https?:\/\//i.test(trimmedUrl)) {
      return `https://${trimmedUrl}`
    }
    return trimmedUrl
  }

  // ---------- PROXMOX / VM PART ----------
  const [nodes, setNodes] = useState([])
  const [selectedNode, setSelectedNode] = useState('')
  const [vms, setVms] = useState([])

  const [vmLoading, setVmLoading] = useState(false)
  const [vmError, setVmError] = useState('')

  // create-VM form
  const [createName, setCreateName] = useState('')
  const [creating, setCreating] = useState(false)

  // Hard-coded template info for now
  const TEMPLATE_VMID = 101
  const DEFAULT_CORES = 2
  const DEFAULT_MEMORY_MB = 2048
  const DEFAULT_STORAGE = 'local'

  // Load nodes once
  useEffect(() => {
    const fetchNodes = async () => {
      try {
        setVmError('')
        const res = await fetch(`${API_BASE_URL}/api/proxmox/nodes`)
        if (!res.ok) throw new Error('Failed to load nodes')
        const data = await res.json()

        setNodes(data)

        if (data.length > 0) {
          const firstNode = data[0].node || data[0].id?.split('/').pop()
          setSelectedNode(firstNode)
          await fetchVms(firstNode)
        }
      } catch (err) {
        console.error(err)
        setVmError('ไม่สามารถโหลดข้อมูล Proxmox nodes ได้')
      }
    }

    fetchNodes()
  }, [])

  const fetchVms = async (node) => {
    try {
      setVmLoading(true)
      setVmError('')
      const res = await fetch(
        `${API_BASE_URL}/api/proxmox/vms?node=${encodeURIComponent(node)}`
      )
      if (!res.ok) throw new Error('Failed to load VMs')
      const data = await res.json()
      setVms(data)
    } catch (err) {
      console.error(err)
      setVmError('โหลดรายการ VM ไม่สำเร็จ')
    } finally {
      setVmLoading(false)
    }
  }

  const handleNodeChange = async (e) => {
    const node = e.target.value
    setSelectedNode(node)
    if (node) {
      await fetchVms(node)
    }
  }

  const handleStart = async (vmid) => {
    if (!selectedNode) return
    try {
      setVmError('')
      await fetch(
        `${API_BASE_URL}/api/proxmox/vms/${encodeURIComponent(
          selectedNode
        )}/${vmid}/start`,
        {
          method: 'POST',
        }
      )
      await fetchVms(selectedNode)
    } catch (err) {
      console.error(err)
      setVmError('สั่ง start VM ไม่สำเร็จ')
    }
  }

  const handleStop = async (vmid) => {
    if (!selectedNode) return
    try {
      setVmError('')
      await fetch(
        `${API_BASE_URL}/api/proxmox/vms/${encodeURIComponent(
          selectedNode
        )}/${vmid}/stop`,
        {
          method: 'POST',
        }
      )
      await fetchVms(selectedNode)
    } catch (err) {
      console.error(err)
      setVmError('สั่ง stop VM ไม่สำเร็จ')
    }
  }

  const handleCreateVm = async (e) => {
    e.preventDefault()
    if (!selectedNode || !createName.trim()) return

    try {
      setCreating(true)
      setVmError('')

      const res = await fetch(`${API_BASE_URL}/api/proxmox/vms/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          node: selectedNode,
          template_vmid: TEMPLATE_VMID,
          name: createName.trim(),
          cores: DEFAULT_CORES,
          memory: DEFAULT_MEMORY_MB,
          storage: DEFAULT_STORAGE,
        }),
      })

      const data = await res.json()
      console.log('Create VM response:', data)

      await fetchVms(selectedNode)
      setCreateName('')
      alert(
        `ส่งคำสั่งสร้าง VM แล้ว\n\nสถานะจาก backend: ${
          data.status || 'เช็คใน Proxmox UI'
        }`
      )
    } catch (err) {
      console.error(err)
      setVmError('สร้าง VM ไม่สำเร็จ')
    } finally {
      setCreating(false)
    }
  }

  // ---------- RENDER ----------
  return (
    <div style={{ padding: 16 }}>
      {/* GRAFANA SECTION */}
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

      <div
        style={{
          marginTop: 16,
          height: '60vh',
          border: '1px solid #ddd',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <iframe
          title="grafana-dashboard"
          src={normalizeURL(dashboardURL)}
          style={{
            width: '100%',
            height: '100%',
            border: 0,
            transform: 'scale(1)',
            transformOrigin: 'top left',
          }}
        />
      </div>

      {/* PROXMOX SECTION */}
      <hr style={{ margin: '24px 0' }} />
      <h2>VM Management (Proxmox)</h2>

      {roleError && (
        <div style={{ color: 'red', marginBottom: 8 }}>{roleError}</div>
      )}

      {vmError && (
        <div style={{ color: 'red', marginBottom: 8 }}>
          {vmError}
        </div>
      )}

      {role === 1 && (
        <p style={{ marginBottom: 8 }}>
          บทบาทของคุณ: <b>Student</b> – สามารถสร้าง VM ของตัวเองจาก template
          ได้
        </p>
      )}
      {role === 2 && (
        <p style={{ marginBottom: 8 }}>
          บทบาทของคุณ: <b>Staff/Admin</b>
        </p>
      )}

      <div style={{ marginBottom: 12 }}>
        <label>
          Node:&nbsp;
          <select value={selectedNode} onChange={handleNodeChange}>
            <option value="">-- เลือก node --</option>
            {nodes.map((n) => {
              const nodeName = n.node || n.id?.split('/').pop()
              return (
                <option key={nodeName} value={nodeName}>
                  {nodeName}
                </option>
              )
            })}
          </select>
        </label>
        <button
          style={{ marginLeft: 8 }}
          onClick={() => selectedNode && fetchVms(selectedNode)}
        >
          Refresh VMs
        </button>
      </div>

      {/* Create VM form – only for students */}
      {role === 1 && (
        <form
          onSubmit={handleCreateVm}
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'center',
            marginBottom: 16,
            flexWrap: 'wrap',
          }}
        >
          <input
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            placeholder={`ชื่อ VM ใหม่ (template=${TEMPLATE_VMID})`}
            style={{ padding: 6, minWidth: 240 }}
          />
          <button type="submit" disabled={!selectedNode || creating}>
            {creating ? 'Creating…' : 'Create VM from Template'}
          </button>
        </form>
      )}

      {/* VM table */}
      {vmLoading ? (
        <p>กำลังโหลดรายการ VM ...</p>
      ) : vms.length === 0 ? (
        <p>ยังไม่มี VM ใน node นี้ หรือโหลดข้อมูลไม่สำเร็จ</p>
      ) : (
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 14,
          }}
        >
          <thead>
            <tr>
              <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                VMID
              </th>
              <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                Name
              </th>
              <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                Status
              </th>
              <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                Type
              </th>
              <th style={{ borderBottom: '1px solid #ddd' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {vms.map((vm) => (
              <tr key={vm.vmid}>
                <td style={{ padding: '4px 0' }}>{vm.vmid}</td>
                <td>{vm.name}</td>
                <td>{vm.status}</td>
                <td>{vm.type}</td>
                <td>
                  <button
                    onClick={() => handleStart(vm.vmid)}
                    style={{ marginRight: 4 }}
                  >
                    Start
                  </button>
                  <button onClick={() => handleStop(vm.vmid)}>Stop</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
