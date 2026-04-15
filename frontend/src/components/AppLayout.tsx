import { Layout, Menu, Avatar, Typography, Space } from 'antd'
import {
  DashboardOutlined, UserOutlined, ShoppingOutlined,
  FileTextOutlined, SettingOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

const { Sider, Content, Header } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/accounts', icon: <UserOutlined />, label: '账号管理' },
  { key: '/products', icon: <ShoppingOutlined />, label: '商品配置' },
  { key: '/logs', icon: <FileTextOutlined />, label: '申购日志' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { username, clearAuth } = useAuthStore()

  const handleLogout = () => {
    clearAuth()
    navigate('/login')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ padding: '16px', textAlign: 'center', color: '#fff', fontSize: 16, fontWeight: 'bold' }}>
          i茅台抢购
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
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Space>
            <Avatar icon={<UserOutlined />} />
            <Text>{username}</Text>
            <LogoutOutlined onClick={handleLogout} style={{ cursor: 'pointer', color: '#999' }} />
          </Space>
        </Header>
        <Content style={{ margin: '24px', background: '#fff', padding: 24, borderRadius: 8, minHeight: 360 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
