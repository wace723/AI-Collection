import { useEffect, useState } from 'react'
import { Card, Col, Empty, Row, Statistic } from 'antd'
import { getDailyDashboard } from '../../api/dashboard'
import type { DailyDashboard } from '../../types/api'
import { PieChart } from '../../components/Charts'

const TIER_LABEL: Record<string, string> = {
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
  NONE: '未定档',
}

const AGE_LABEL: Record<string, string> = {
  '0_7': '0-7天',
  '8_15': '8-15天',
  '16_30': '16-30天',
  '31_90': '31-90天',
  '90_PLUS': '90天以上',
  UNKNOWN: '未知',
}

/** 日大盘：核心指标卡片 + 风险档分布饼图 + 账龄分布饼图 */
export default function DailyDashboardTab() {
  const [data, setData] = useState<DailyDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getDailyDashboard())
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

  const riskData = data
    ? Object.entries(data.risk_distribution)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ type: TIER_LABEL[k] ?? k, value: v }))
    : []

  const ageData = data
    ? Object.entries(data.age_distribution)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ type: AGE_LABEL[k] ?? k, value: v }))
    : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="当日新增任务" value={data?.new_tasks ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="当日回款" value={data?.paid_count ?? 0} suffix="笔" />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="当日已处理"
              value={data?.processed_count ?? 0}
              suffix="笔"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="当日回款率"
              value={data ? (data.paid_rate * 100).toFixed(1) : '0.0'}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="风险档分布（未支付订单）" loading={loading}>
            {riskData.length > 0 ? (
              <PieChart data={riskData} angleField="value" colorField="type" />
            ) : (
              <Empty description="暂无未支付订单" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="账龄分布（未支付订单）" loading={loading}>
            {ageData.length > 0 ? (
              <PieChart data={ageData} angleField="value" colorField="type" />
            ) : (
              <Empty description="暂无未支付订单" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
