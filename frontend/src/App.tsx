import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Goals from './pages/Goals'
import Activities from './pages/Activities'
import Profile from './pages/Profile'
import Records from './pages/Records'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="goals" element={<Goals />} />
        <Route path="records" element={<Records />} />
        <Route path="activities" element={<Activities />} />
        <Route path="profile" element={<Profile />} />
      </Route>
    </Routes>
  )
}
