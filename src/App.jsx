import { Routes, Route, Link } from 'react-router-dom'
import Home from './pages/Home.jsx'
import Settings from './pages/Settings.jsx'

export default function App() {
  return (
    <div>
      {/* nav ง่ายๆ */}
      <nav style={{ padding: 12, borderBottom: '1px solid #ddd' }}>
        <Link to="/" style={{ marginRight: 12 }}>Home</Link>
        <Link to="/settings">Settings</Link>
      </nav>

      {/* outlet */}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  )
}
