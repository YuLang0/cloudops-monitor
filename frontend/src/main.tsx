import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Spinner } from './components/ui'
import { AppProvider, useApp } from './context/AppContext'
import './index.css'
import { DashboardPage } from './pages/DashboardPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { LoginPage } from './pages/LoginPage'
import { ServerDetailPage } from './pages/ServerDetailPage'
import { ServersPage } from './pages/ServersPage'

function App() {
  const { user } = useApp()
  if (user === undefined) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label="세션 확인 중…" />
      </div>
    )
  }
  // 로그인하지 않으면 어떤 경로로 들어와도 로그인 화면만 보인다.
  // (화면을 숨기는 것은 편의일 뿐이고, 실제 보호는 백엔드가 모든 API 에서 인증을 확인해 수행한다)
  if (user === null) return <LoginPage />
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="servers/:id" element={<ServerDetailPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
)
