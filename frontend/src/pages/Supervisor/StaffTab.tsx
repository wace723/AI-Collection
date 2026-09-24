import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Statistic, Row, Col } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getStaffPerformance } from '../../api/supervisor'
import type { StaffPerformance } from '../../types/api'

/** 任务统计 Tab：各催收员任务完成情况 + 团队处理中任务 */
export default function StaffTab() {
  const [data, setData] = useState<StaffPerformance[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      setData(await getStaffPerformance())
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const totalPending = data.reduce((s, d) => s + d.pending_count, 0)
  const totalInProgress = data.reduce((s, d) => s + d.in_progress_count, 0)
  const totalDone = data.reduce((s, d) => s + d.done_count, 0)
  const totalPaid = data.reduce((s, d) => s + d.paid_count, 0)

  const columns: ColumnsType<StaffPerformance> = [
    { title: '催收员', dataIndex: 'display_name', width: 120 },
    { title: '用户名', dataIndex: 'username', width: 120 },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="green">在职</Tag> : <Tag>停用</Tag>,
    },
    { title: '待处理', dataIndex: 'pending_count', width: 90 },
    { title: '进行中', dataIndex: 'in_progress_count', width: 90 },
    { title: '已完成', dataIndex: 'done_count', width: 90 },
    { title: '回款数', dataIndex: 'paid_count', width: 90 },
    {
      title: '回款率',
      dataIndex: 'paid_rate',
      width: 100,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    { title: '当天已接通', dataIndex: 'today_reached', width: 110 },
    { title: '当天未接通', dataIndex: 'today_unreached', width: 110 },
    { title: '当天待处理', dataIndex: 'today_pending', width: 110 },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="团队待处理任务" value={totalPending} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="团队处理中任务" value={totalInProgress} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="团队已完成" value={totalDone} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="团队回款数" value={totalPaid} suffix="笔" />
          </Card>
        </Col>
      </Row>

      <Card
        title="任务统计"
        extra={
          <Button icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        }
      >
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={false}
        />
      </Card>
    </div>
  )
}
