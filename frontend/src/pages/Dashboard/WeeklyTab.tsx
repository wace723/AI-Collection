import { useEffect, useMemo, useState } from 'react'
import { Card, Empty, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getWeeklyDashboard } from '../../api/dashboard'
import type { CollectorPerformance, DailyTrendPoint } from '../../types/api'
import { LineChart } from '../../components/Charts'

/** 周大盘：7 日趋势折线 + 催收员绩效排名表 */
export default function WeeklyDashboardTab() {
  const [trend, setTrend] = useState<DailyTrendPoint[]>([])
  const [ranking, setRanking] = useState<CollectorPerformance[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await getWeeklyDashboard()
      setTrend(d.trend)
      setRanking(d.collector_ranking)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  // 完成率 + 回款率双折线（长格式数据）
  const lineData = useMemo(() => {
    const completion = trend.map((p) => ({
      date: p.date,
      type: '完成率',
      value: +(p.completion_rate * 100).toFixed(1),
    }))
    const paid = trend.map((p) => ({
      date: p.date,
      type: '回款率',
      value: +(p.paid_rate * 100).toFixed(1),
    }))
    return [...completion, ...paid]
  }, [trend])

  const rankingColumns: ColumnsType<CollectorPerformance> = [
    {
      title: '排名',
      render: (_v, _r, idx) => idx + 1,
      width: 70,
    },
    { title: '催收员', dataIndex: 'display_name' },
    { title: '用户名', dataIndex: 'username' },
    // 后端已按 (-paid_count, collector_id) 排序；不在前端再排，避免丢失次级排序且保证排名列（基于数组位置）一致
    { title: '回款数', dataIndex: 'paid_count' },
  ]

  if (error) {
    return (
      <Card>
        <Empty description={`加载失败：${error}`} />
      </Card>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="本周每日趋势（完成率 / 回款率 %）" loading={loading}>
        {lineData.length > 0 ? (
          <LineChart data={lineData} xField="date" yField="value" colorField="type" />
        ) : (
          <Empty description="暂无趋势数据" />
        )}
      </Card>

      <Card title="催收员绩效排名（按回款数）" loading={loading}>
        {ranking.length > 0 ? (
          <Table
            columns={rankingColumns}
            dataSource={ranking.map((r, i) => ({ ...r, key: i }))}
            pagination={false}
            size="small"
          />
        ) : (
          <Empty description="本周暂无回款记录" />
        )}
      </Card>
    </div>
  )
}
