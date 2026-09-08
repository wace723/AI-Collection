import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
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
          {/* infra-001 不加路由守卫，infra-002 接入 */}
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/workbench" replace />} />
            <Route path="workbench" element={<Workbench />} />
            <Route path="supervisor" element={<Supervisor />} />
            <Route path="config" element={<Config />} />
            <Route path="dashboard" element={<Dashboard />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
