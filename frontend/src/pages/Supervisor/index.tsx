import { useEffect, useState, Suspense, lazy } from 'react'
import { Alert, Card, Tabs } from 'antd'
import { getMe } from '../../api/auth'

// 懒加载三个 Tab，减小主 chunk
const UsersTab = lazy(() => import('./UsersTab'))
const StaffTab = lazy(() => import('./StaffTab'))
const ReassignTab = lazy(() => import('./ReassignTab'))

/** 主管视图（SUPERVISOR/ADMIN）：员工管理 / 任务改派 / 绩效统计 */
export default function Supervisor() {
  const [role, setRole] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    getMe()
      .then((u) => setRole(u.role))
      .finally(() => setLoaded(true))
  }, [])

  if (!loaded) {
    return <Card title="主管视图" loading />
  }

  if (role !== 'SUPERVISOR' && role !== 'ADMIN') {
    return (
      <Card title="主管视图">
        <Alert
          type="warning"
          message="权限不足"
          description="主管视图仅主管/管理员可访问。"
          showIcon
        />
      </Card>
    )
  }

  return (
    <Card title="主管视图">
      <Tabs
        defaultActiveKey="staff"
        items={[
          {
            key: 'staff',
            label: '绩效统计',
            children: (
              <Suspense fallback={<Card loading />}>
                <StaffTab />
              </Suspense>
            ),
          },
          {
            key: 'users',
            label: '员工管理',
            children: (
              <Suspense fallback={<Card loading />}>
                <UsersTab />
              </Suspense>
            ),
          },
          {
            key: 'reassign',
            label: '任务改派',
            children: (
              <Suspense fallback={<Card loading />}>
                <ReassignTab />
              </Suspense>
            ),
          },
        ]}
      />
    </Card>
  )
}
