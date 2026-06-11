import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuthStore } from './stores/auth'
import { useUiStore } from './stores/ui'
import { authApi } from './api/client'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import JobDetail from './pages/JobDetail'
import Templates from './pages/Templates'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Groups from './pages/Groups'
import Providers from './pages/Providers'
import Login from './pages/Login'
import SceneEditor from './pages/SceneEditor'
import Chat from './pages/Chat'
import Avatars from './pages/Avatars'
import { MediaLibrary } from './pages/MediaLibrary'
import { AssetDetail } from './pages/AssetDetail'
import MCPServersPage from './pages/MCPServersPage'
import ModelManagement from './pages/admin/ModelManagement'
import AdminLogs from './pages/admin/AdminLogs'
import { ThemeProvider } from './components/ThemeProvider'
import { Toaster } from './components/ui/toaster'
import { NotificationCenter } from './components/NotificationCenter'
import { Loader2 } from 'lucide-react'

function AppRoutes({ isAuthenticated }: { isAuthenticated: boolean }) {
  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="editor/:jobId" element={<SceneEditor />} />
        <Route path="templates" element={<Templates />} />
        <Route path="settings" element={<Settings />} />
        <Route path="admin" element={<Admin />} />
        <Route path="admin/providers" element={<Providers />} />
        <Route path="admin/mcp-servers" element={<MCPServersPage />} />
        <Route path="admin/groups" element={<Groups />} />
        <Route path="admin/models" element={<ModelManagement />} />
        <Route path="admin/logs" element={<AdminLogs />} />
        <Route path="media" element={<MediaLibrary />} />
        <Route path="media/asset/:id" element={<AssetDetail />} />
        <Route path="avatars" element={<Avatars />} />
        <Route path="chat" element={<Chat />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  const { isAuthenticated, setAuth } = useAuthStore()
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    authApi
      .getMe()
      .then(async (response) => {
        setAuth(response.data)
        await useUiStore.getState().hydrateSidebarPreference()
        setIsLoading(false)
      })
      .catch(() => {
        // no-op: user not authenticated
        useUiStore.getState().resetUiPreferences()
        setIsLoading(false)
      })
  }, [setAuth])

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <ThemeProvider>
      <BrowserRouter>
        <AppRoutes isAuthenticated={isAuthenticated} />
        <Toaster />
        <NotificationCenter />
      </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
