import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
import RequireAuth from './components/RequireAuth'
import Login from './pages/Login'
import Workbench from './pages/Workbench'
import Supervisor from './pages/Supervisor'
import Config from './pages/Config'
import Dashboard from './pages/Dashboard'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* 受保护路由：无 token 跳 /login */}
          <Route element={<RequireAuth />}>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<Navigate to="/workbench" replace />} />
              <Route path="workbench" element={<Workbench />} />
              <Route path="supervisor" element={<Supervisor />} />
              <Route path="config" element={<Config />} />
              <Route path="dashboard" element={<Dashboard />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
