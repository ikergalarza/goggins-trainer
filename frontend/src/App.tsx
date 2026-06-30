import { Routes, Route, Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import Goals from './pages/Goals'
import Activities from './pages/Activities'
import ActivityDetail from './pages/ActivityDetail'
import Profile from './pages/Profile'
import Records from './pages/Records'
import Plan from './pages/Plan'
import Chat from './pages/Chat'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-gray-500">Cargando...</div>
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireMaster({ children }: { children: ReactNode }) {
  const { isMaster } = useAuth()
  if (!isMaster) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="goals" element={<Goals />} />
          <Route path="plan" element={<Plan />} />
          <Route path="chat" element={<Chat />} />
          <Route path="records" element={<Records />} />
          <Route path="activities" element={<Activities />} />
          <Route path="activities/:activityId" element={<ActivityDetail />} />
          <Route path="profile" element={<Profile />} />
          <Route path="admin" element={<RequireMaster><Admin /></RequireMaster>} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
