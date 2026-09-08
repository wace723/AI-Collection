import { Layout, Menu } from 'antd'
import { DesktopOutlined, DashboardOutlined, SettingOutlined, TeamOutlined } from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Sider, Header, Content } = Layout

const menuItems = [
  { key: '/workbench', icon: <DesktopOutlined />, label: '催收工作台' },
  { key: '/supervisor', icon: <TeamOutlined />, label: '主管视图' },
  { key: '/config', icon: <SettingOutlined />, label: '配置后台' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: '数据大盘' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible>
        <div style={{ height: 48, color: '#fff', textAlign: 'center', lineHeight: '48px', fontSize: 16 }}>
          平台使用费催收
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px' }}>
          <span style={{ fontSize: 16, fontWeight: 500 }}>AI 辅助催收系统</span>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
