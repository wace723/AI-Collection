import { useEffect, useState, Suspense, lazy } from 'react'
import { Alert, Card, Tabs } from 'antd'
import { getMe } from '../../api/auth'

// 懒加载三个 Tab 子组件，使图表库随大盘页按需加载
const DailyDashboardTab = lazy(() => import('./DailyTab'))
const WeeklyDashboardTab = lazy(() => import('./WeeklyTab'))
const MonthlyDashboardTab = lazy(() => import('./MonthlyTab'))

/** 数据大盘（仅 SUPERVISOR/ADMIN） */
export default function Dashboard() {
  const [role, setRole] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    getMe()
      .then((u) => setRole(u.role))
      .catch(() => setLoadError(true))
      .finally(() => setLoaded(true))
  }, [])

  if (!loaded) {
    return <Card title="数据大盘" loading />
  }

  if (loadError) {
    return (
      <Card title="数据大盘">
        <Alert
          type="error"
          message="加载用户信息失败"
          description="无法获取当前用户信息，请检查网络后刷新重试。"
          showIcon
        />
      </Card>
    )
  }

  if (role !== 'SUPERVISOR' && role !== 'ADMIN') {
    return (
      <Card title="数据大盘">
        <Alert
          type="warning"
          message="权限不足"
          description="数据大盘仅主管/管理员可查看。"
          showIcon
        />
      </Card>
    )
  }

  return (
    <Card title="数据大盘" styles={{ body: { paddingTop: 16 } }}>
      <Tabs
        defaultActiveKey="daily"
        items={[
          {
            key: 'daily',
            label: '日大盘',
            children: (
              <Suspense fallback={<Card loading />}>
                <DailyDashboardTab />
              </Suspense>
            ),
          },
          {
            key: 'weekly',
            label: '周大盘',
            children: (
              <Suspense fallback={<Card loading />}>
                <WeeklyDashboardTab />
              </Suspense>
            ),
          },
          {
            key: 'monthly',
            label: '月大盘',
            children: (
              <Suspense fallback={<Card loading />}>
                <MonthlyDashboardTab />
              </Suspense>
            ),
          },
        ]}
      />
    </Card>
  )
}
