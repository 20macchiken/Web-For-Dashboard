import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { supabase } from '../lib/supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000'

export default function Home() {
  const { user, session, isStaff } = useAuth() // Destructured isStaff

  // Helper function to get auth headers
  const getAuthHeaders = () => {
    if (!session?.access_token) {
      throw new Error('No authentication token available')
    }
    return {
      Authorization: `Bearer ${session.access_token}`,
      'Content-Type': 'application/json',
    }
  }

  // ---------- GRAFANA PART ----------
  const storageKey = user?.email ? `grafanaUrl:${user.email}` : 'grafanaUrl:guest'

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

  const [userProxmoxVmid, setUserProxmoxVmid] = useState(null)

  // Load student's Proxmox VMID (if any) from Supabase Users table
  useEffect(() => {
    const loadUserProxmox = async () => {
      if (!user?.id) return
      try {
        const { data, error } = await supabase
          .from('Users')
          .select('Proxmox')
          .eq('id', user.id)
          .maybeSingle()

        if (error) {
          console.error('Error loading user Proxmox:', error)
          return
        }
        setUserProxmoxVmid(data?.Proxmox ?? null)
      } catch (err) {
        console.error('Unexpected error loading user Proxmox:', err)
      }
    }

    loadUserProxmox()
  }, [user?.id])

  // create-VM form
  const [createName, setCreateName] = useState('')
  const [creating, setCreating] = useState(false)

  // hard-coded template info for now (you can change later)
  const TEMPLATE_VMID = 101
  const DEFAULT_CORES = 2
  const DEFAULT_MEMORY_MB = 2048
  const DEFAULT_STORAGE = 'local'

  // load nodes once
  useEffect(() => {
    const fetchNodes = async () => {
      try {
        setVmError('')
        const res = await fetch(`${API_BASE_URL}/api/proxmox/nodes`, {
          headers: getAuthHeaders(),
        })
        if (!res.ok) {
          if (res.status === 401) {
            throw new Error('Authentication failed - please log in again')
          }
          throw new Error('Failed to load nodes')
        }
        const data = await res.json()

        setNodes(data)

        if (data.length > 0) {
          // Proxmox returns { node: "proxmox-node-b", ... }
          const firstNode = data[0].node || data[0].id?.split('/').pop()
          setSelectedNode(firstNode)
        }
      } catch (err) {
        console.error(err)
        setVmError(err.message || 'โหลดข้อมูล Proxmox nodes ไม่สำเร็จ')
      }
    }

    fetchNodes()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchVms = async (node) => {
    if (!node) return
    setVmLoading(true)
    setVmError('')
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/proxmox/vms?node=${encodeURIComponent(node)}`,
        {
          headers: getAuthHeaders(),
        }
      )
      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('Authentication failed - please log in again')
        }
        throw new Error('Failed to load VMs')
      }
      const data = await res.json()
      setVms(data)
    } catch (err) {
      console.error(err)
      setVmError(err.message || 'โหลดข้อมูล VMs ไม่สำเร็จ')
    } finally {
      setVmLoading(false)
    }
  }

  useEffect(() => {
    if (selectedNode) {
      fetchVms(selectedNode)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode])

  const handleNodeChange = (e) => {
    const newNode = e.target.value
    setSelectedNode(newNode)
  }

  const handleStart = async (vmid) => {
    if (!selectedNode) return
    try {
      setVmError('')

      const res = await fetch(
        `${API_BASE_URL}/api/proxmox/vms/${encodeURIComponent(
          selectedNode
        )}/${vmid}/start`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
        }
      )

      if (!res.ok) {
        let message = 'สั่ง start VM ไม่สำเร็จ'
        try {
          const data = await res.json()
          if (data?.error) message = data.error
        } catch (_) {
          // ignore JSON parse error
        }
        throw new Error(message)
      }

      await fetchVms(selectedNode)
    } catch (err) {
      console.error(err)
      setVmError(err.message || 'สั่ง start VM ไม่สำเร็จ')
    }
  }

  const handleStop = async (vmid) => {
    if (!selectedNode) return
    try {
      setVmError('')

      const res = await fetch(
        `${API_BASE_URL}/api/proxmox/vms/${encodeURIComponent(
          selectedNode
        )}/${vmid}/stop`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
        }
      )

      if (!res.ok) {
        let message = 'สั่ง stop VM ไม่สำเร็จ'
        try {
          const data = await res.json()
          if (data?.error) message = data.error
        } catch (_) {
          // ignore JSON parse error
        }
        throw new Error(message)
      }

      await fetchVms(selectedNode)
    } catch (err) {
      console.error(err)
      setVmError(err.message || 'สั่ง stop VM ไม่สำเร็จ')
    }
  }

  const handleDelete = async (vmid) => {
    if (!selectedNode) return

    if (
      !window.confirm(
        'คุณแน่ใจหรือไม่ว่าจะลบ VM นี้? การลบนี้ไม่สามารถย้อนกลับได้.'
      )
    ) {
      return
    }

    try {
      setVmError('')

      const res = await fetch(
        `${API_BASE_URL}/api/proxmox/vms/${encodeURIComponent(
          selectedNode
        )}/${vmid}/delete`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
        }
      )

      let data = {}
      try {
        data = await res.json()
      } catch (_) {
        // ignore if no JSON body
      }

      if (!res.ok) {
        const message = data?.error || 'ลบ VM ไม่สำเร็จ'
        throw new Error(message)
      }

      console.log('Delete VM response:', data)

      // If it was this student's own VM, clear local mapping
      if (
        userProxmoxVmid != null &&
        String(vmid) === String(userProxmoxVmid)
      ) {
        setUserProxmoxVmid(null)
      }

      await fetchVms(selectedNode)
    } catch (err) {
      console.error(err)
      setVmError(err.message || 'ลบ VM ไม่สำเร็จ')
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
        headers: getAuthHeaders(),
        body: JSON.stringify({
          node: selectedNode,
          template_vmid: TEMPLATE_VMID,
          name: createName.trim(),
          cores: DEFAULT_CORES,
          memory: DEFAULT_MEMORY_MB,
          storage: DEFAULT_STORAGE,
        }),
      })

      let data = {}
      try {
        data = await res.json()
      } catch (_) {
        // ignore if no JSON body
      }

      if (!res.ok) {
        const message = data?.error || 'สร้าง VM ไม่สำเร็จ'
        throw new Error(message)
      }

      console.log('Create VM response:', data)

      // If backend assigned a VMID (for students this is their only VM),
      // remember it locally so we know which row is controllable.
      if (data?.vmid) {
        setUserProxmoxVmid(String(data.vmid))
      }

      await fetchVms(selectedNode)
      setCreateName('')
      alert(
        `ส่งคำสั่งสร้าง VM แล้ว\n\nสถานะจาก backend: ${
          data.status || 'เช็คใน Proxmox UI'
        }`
      )
    } catch (err) {
      console.error(err)
      setVmError(err.message || 'สร้าง VM ไม่สำเร็จ')
    } finally {
      setCreating(false)
    }
  }

    // Group VMs: ones owned by this user vs others (templates/other instances)
  const ownedVms = vms.filter(
    (vm) =>
      userProxmoxVmid != null &&
      String(vm.vmid) === String(userProxmoxVmid)
  )

  const otherVms = vms.filter(
    (vm) =>
      !(
        userProxmoxVmid != null &&
        String(vm.vmid) === String(userProxmoxVmid)
      )
  )


  // ---------- RENDER ----------
  return (
    <div style={{ padding: 16 }}>
      {/* GRAFANA SECTION */}
      <h2>URL Viewer</h2>

      <p style={{ marginTop: 8, marginBottom: 8 }}>
        Welcome, {user?.email} — role:{' '}
        {isStaff ? 'Staff / Admin' : 'Student'}
      </p>

      <label style={{ fontWeight: 'bold' }}>
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
          borderRadius: 4,
          overflow: 'hidden',
        }}
      >
        {normalizeURL(dashboardURL) ? (
          <iframe
            src={normalizeURL(dashboardURL)}
            title="Grafana Dashboard"
            style={{ width: '100%', height: '100%', border: 'none' }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#999',
            }}
          >
            ใส่ URL ของ Grafana dashboard ด้านบน
          </div>
        )}
      </div>

      <hr style={{ margin: '24px 0' }} />

      {/* PROXMOX SECTION */}
      <h2>VM Management (Proxmox)</h2>

      <p style={{ color: '#555' }}>
        บทบาทของคุณ: {isStaff ? 'Staff / Admin' : 'Student'}
      </p>

      {/* Node selection */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ marginRight: 8 }}>Node:</label>
        <select
          value={selectedNode}
          onChange={handleNodeChange}
          style={{ padding: 4 }}
        >
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

        <button
          onClick={() => fetchVms(selectedNode)}
          style={{ marginLeft: 8, padding: '4px 8px' }}
        >
          Refresh VMs
        </button>
      </div>

      {/* Error message */}
      {vmError && (
        <div style={{ color: 'red', marginBottom: 12 }}>{vmError}</div>
      )}

      {/* Create VM form (both staff & student can see; backend enforces 1-VM/student) */}
      <form
        onSubmit={handleCreateVm}
        style={{ marginBottom: 16, display: 'flex', gap: 8 }}
      >
        <input
          type="text"
          placeholder={`ชื่อ VM ใหม่ (template=${TEMPLATE_VMID})`}
          value={createName}
          onChange={(e) => setCreateName(e.target.value)}
          style={{ flex: 1, padding: 4 }}
        />
        <button type="submit" disabled={creating || !selectedNode}>
          {creating ? 'กำลังสร้าง...' : 'Create VM from Template'}
        </button>
      </form>

      {/* VMs table */}
      {vmLoading ? (
        <p>กำลังโหลดข้อมูล VM...</p>
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
              <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                Actions
              </th>
            </tr>
          </thead>

          <tbody>
            {/* 1) Templates / other VMs */}
            {otherVms.map((vm) => {
              const isOwner =
                userProxmoxVmid != null &&
                String(vm.vmid) === String(userProxmoxVmid)

              return (
                <tr key={vm.vmid}>
                  <td style={{ padding: '4px 0' }}>{vm.vmid}</td>
                  <td>{vm.name}</td>
                  <td>{vm.status}</td>
                  <td>{vm.type}</td>
                  <td>
                    {isStaff ? (
                      <>
                        <button
                          onClick={() => handleStart(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Start
                        </button>
                        <button
                          onClick={() => handleStop(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Stop
                        </button>
                        <button onClick={() => handleDelete(vm.vmid)}>Delete</button>
                      </>
                    ) : isOwner ? (
                      <>
                        <button
                          onClick={() => handleStart(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Start
                        </button>
                        <button
                          onClick={() => handleStop(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Stop
                        </button>
                        <button onClick={() => handleDelete(vm.vmid)}>Delete</button>
                      </>
                    ) : (
                      <span
                        style={{
                          color: '#888',
                          fontSize: '12px',
                          fontStyle: 'italic',
                        }}
                      >
                        Read Only
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}

            {/* 2) Separator before student's own VM(s) */}
            {!isStaff && ownedVms.length > 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '8px 0' }}>
                  <hr
                    style={{
                      border: 'none',
                      borderTop: '1px dashed #666',
                      margin: '8px 0',
                    }}
                  />
                  <div
                    style={{
                      textAlign: 'center',
                      fontSize: 12,
                      color: '#ccc',
                      fontStyle: 'italic',
                    }}
                  >
                    Your VM
                  </div>
                </td>
              </tr>
            )}

            {/* 3) Student’s own VM(s) */}
            {ownedVms.map((vm) => {
              const isOwner =
                userProxmoxVmid != null &&
                String(vm.vmid) === String(userProxmoxVmid)

              return (
                <tr key={vm.vmid}>
                  <td style={{ padding: '4px 0' }}>{vm.vmid}</td>
                  <td>{vm.name}</td>
                  <td>{vm.status}</td>
                  <td>{vm.type}</td>
                  <td>
                    {isStaff ? (
                      <>
                        <button
                          onClick={() => handleStart(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Start
                        </button>
                        <button
                          onClick={() => handleStop(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Stop
                        </button>
                        <button onClick={() => handleDelete(vm.vmid)}>Delete</button>
                      </>
                    ) : isOwner ? (
                      <>
                        <button
                          onClick={() => handleStart(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Start
                        </button>
                        <button
                          onClick={() => handleStop(vm.vmid)}
                          style={{ marginRight: 4 }}
                        >
                          Stop
                        </button>
                        <button onClick={() => handleDelete(vm.vmid)}>Delete</button>
                      </>
                    ) : (
                      <span
                        style={{
                          color: '#888',
                          fontSize: '12px',
                          fontStyle: 'italic',
                        }}
                      >
                        Read Only
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
