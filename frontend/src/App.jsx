import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Inbox from './pages/Inbox.jsx'
import EmailDetails from './pages/EmailDetails.jsx'
import Tasks from './pages/Tasks.jsx'
import Settings from './pages/Settings.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/emails/:id" element={<EmailDetails />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
