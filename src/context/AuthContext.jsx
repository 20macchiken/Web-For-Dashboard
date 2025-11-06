import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const storedUser = localStorage.getItem('currentUser')
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser))
      } catch (e) {
        localStorage.removeItem('currentUser')
      }
    }
    setLoading(false)
  }, [])

  const login = (username, password) => {
    // For now, we'll accept any username/password
    const userInfo = {
      username: username.trim(),
      loginTime: new Date().toISOString()
    }

    const users = JSON.parse(localStorage.getItem('users') || '{}')

    if (users[username]) {
      if (users[username].password !== password) {
        return false // Password doesn't match
      }
    } else {
      // New user - store their credentials
      users[username] = { password }
      localStorage.setItem('users', JSON.stringify(users))
    }

    setUser(userInfo)
    localStorage.setItem('currentUser', JSON.stringify(userInfo))
    return true
  }

  const logout = () => {
    setUser(null)
    localStorage.removeItem('currentUser')
  }

  const value = {
    user,
    login,
    logout,
    loading,
    isAuthenticated: !!user
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('Error!')
  }
  return context
}
