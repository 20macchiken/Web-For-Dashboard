import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Home from './pages/Home.jsx'
import Settings from './pages/Settings.jsx'
import Logs from './pages/Logs.jsx'
import Login from './pages/Login.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout, isAuthenticated } = useAuth()

  const isLoginPage = location.pathname === '/login'

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div>
      {/* Show navigation only when not on login page and user is authenticated */}
      {!isLoginPage && isAuthenticated && (
        <nav style={{
          padding: 12,
          borderBottom: '1px solid #ddd',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            <Link to="/" style={{ marginRight: 12 }}>Home</Link>
            <Link to="/logs" style={{ marginRight: 12 }}>Logs</Link>
            <Link to="/settings">Settings</Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '14px', color: '#666' }}>
              Welcome, {user?.email}
            </span>
            <button
              onClick={handleLogout}
              style={{
                padding: '6px 12px',
                backgroundColor: '#dc3545',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Logout
            </button>
          </div>
        </nav>
      )}

      {/* Routes */}
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Home />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          }
        />
        <Route
          path="/logs"
          element={
            <ProtectedRoute>
              <Logs />
            </ProtectedRoute>
          }
        />
      </Routes>
    </div>
  )
}
