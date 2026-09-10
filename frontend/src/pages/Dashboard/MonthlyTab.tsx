import { useEffect, useState } from 'react'
import { Card, Col, Empty, Row, Statistic, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getMonthlyDashboard } from '../../api/dashboard'
import type { MonthlyDashboard, TierEffect } from '../../types/api'
import { ColumnChart } from '../../components/Charts'

/** 月大盘：月度欠费率/回款率卡片 + 各档催收效果柱图 */
export default function MonthlyDashboardTab() {
  const [data, setData] = useState<MonthlyDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getMonthlyDashboard())
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  if (error) {
    return (
      <Card>
        <Empty description={`加载失败：${error}`} />
      </Card>
    )
  }

  const tierLabel: Record<string, string> = {
    HIGH: '高风险',
    MEDIUM: '中风险',
    LOW: '低风险',
    NONE: '未定档',
  }

  const barData = data
    ? data.tier_effects.flatMap((t) => [
        {
          tier: tierLabel[t.risk_tier] ?? t.risk_tier,
          type: '已处理',
          value: t.processed,
        },
        {
          tier: tierLabel[t.risk_tier] ?? t.risk_tier,
          type: '回款',
          value: t.paid,
        },
      ])
    : []

  const effectColumns: ColumnsType<TierEffect> = [
    {
      title: '风险档',
      dataIndex: 'risk_tier',
      render: (v: string) => tierLabel[v] ?? v,
    },
    { title: '已处理', dataIndex: 'processed' },
    { title: '回款数', dataIndex: 'paid' },
    {
      title: '回款率',
      dataIndex: 'paid_rate',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="月度欠费率"
              value={data ? (data.unpaid_rate * 100).toFixed(1) : '0.0'}
              suffix="%"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic title="月度回款数" value={data?.paid_count ?? 0} suffix="笔" />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="月度回款率"
              value={data ? (data.paid_rate * 100).toFixed(1) : '0.0'}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card title="各档催收效果对比（已处理 / 回款）" loading={loading}>
        {barData.length > 0 ? (
          <ColumnChart data={barData} xField="tier" yField="value" colorField="type" />
        ) : (
          <Empty description="本月暂无催收处理数据" />
        )}
      </Card>

      <Card title="各档催收效果明细" loading={loading}>
        {data && data.tier_effects.length > 0 ? (
          <Table
            columns={effectColumns}
            dataSource={data.tier_effects.map((t, i) => ({ ...t, key: i }))}
            pagination={false}
            size="small"
          />
        ) : (
          <Empty description="本月暂无催收处理数据" />
        )}
      </Card>
    </div>
  )
}
