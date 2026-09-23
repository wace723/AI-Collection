import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Select,
  Space,
  message,
  Popconfirm,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listTasks, reassignTask, runAssign } from '../../api/tasks'
import { listUsers } from '../../api/users'
import type { Task, UserAccount, RiskTier } from '../../types/api'

const statusLabel: Record<string, string> = {
  PENDING_ASSIGN: '待分配',
  PENDING: '待处理',
  IN_PROGRESS: '处理中',
  DONE: '已完成',
  CANCELLED: '已取消',
}
const statusColor: Record<string, string> = {
  PENDING_ASSIGN: 'default',
  PENDING: 'blue',
  IN_PROGRESS: 'gold',
  DONE: 'green',
  CANCELLED: 'default',
}

/** 任务改派 Tab：主管把任务从 A 催收员改派给 B */
export default function ReassignTab() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [collectors, setCollectors] = useState<UserAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [assigning, setAssigning] = useState(false)
  // taskId → 选中的目标催收员 id
  const [selected, setSelected] = useState<Record<number, number>>({})
  const [riskTier, setRiskTier] = useState<string | undefined>(undefined)
  const [assigneeFilter, setAssigneeFilter] = useState<number | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const PAGE_SIZE = 20

  const load = async (
    opts: { tier?: string; assignee?: number; page?: number } = {}
  ) => {
    const tier = opts.tier ?? riskTier
    const assignee = opts.assignee ?? assigneeFilter
    const p = opts.page ?? page
    setLoading(true)
    try {
      const [taskData, users] = await Promise.all([
        listTasks({
          page: p,
          size: PAGE_SIZE,
          risk_tier: tier as RiskTier | undefined,
          assignee,
        }),
        listUsers(),
      ])
      setTasks(taskData.items)
      setTotal(taskData.total)
      setPage(p)
      setCollectors(users.filter((u) => u.role === 'COLLECTOR' && u.is_active))
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load({ page: 1 })
  }, [])

  const onReassign = async (task: Task) => {
    const targetId = selected[task.id]
    if (!targetId) {
      message.warning('请先选择目标催收员')
      return
    }
    try {
      await reassignTask(task.id, targetId)
      message.success('改派成功')
      setSelected((prev) => {
        const next = { ...prev }
        delete next[task.id]
        return next
      })
      await load()
    } catch {
      /* ignore */
    }
  }

  const onAutoAssign = async () => {
    setAssigning(true)
    try {
      const result = await runAssign()
      if (result.assigned > 0) {
        message.success(`自动分配完成：${result.assigned} 个任务已分配`)
      } else if (result.skipped > 0) {
        message.warning(`无可分配任务（跳过 ${result.skipped} 个，无活跃催收员）`)
      } else {
        message.info('无待分配任务')
      }
      await load({ page: 1 })
    } catch {
      /* ignore */
    } finally {
      setAssigning(false)
    }
  }

  const collectorName = (id: number | null) =>
    collectors.find((c) => c.id === id)?.display_name ??
    (id ? `#${id}` : '未分配')

  const columns: ColumnsType<Task> = [
    { title: '订单号', dataIndex: 'service_fee_order_no', width: 200 },
    { title: '供应商', dataIndex: 'supplier_name', width: 150 },
    { title: '风险档', dataIndex: 'risk_tier', width: 80 },
    { title: '当前负责人', key: 'current', width: 120, render: (_, t) => collectorName(t.assignee_id) },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => <Tag color={statusColor[v]}>{statusLabel[v] ?? v}</Tag>,
    },
    {
      title: '改派给',
      key: 'target',
      width: 200,
      render: (_: unknown, t: Task) => (
        <Select
          size="small"
          style={{ width: 160 }}
          placeholder="选择目标催收员"
          value={selected[t.id]}
          onChange={(v) => setSelected((prev) => ({ ...prev, [t.id]: v }))}
          options={collectors.map((c) => ({
            label: c.display_name,
            value: c.id,
          }))}
          disabled={t.status === 'DONE' || t.status === 'CANCELLED'}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, t: Task) => (
        <Popconfirm
          title={`改派给 ${collectorName(selected[t.id])}？`}
          onConfirm={() => onReassign(t)}
          disabled={!selected[t.id] || t.status === 'DONE' || t.status === 'CANCELLED'}
        >
          <Button
            size="small"
            type="primary"
            disabled={!selected[t.id] || t.status === 'DONE' || t.status === 'CANCELLED'}
          >
            改派
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Card
      title="任务改派"
      extra={
        <Space>
          <Select
            allowClear
            placeholder="风险档"
            style={{ width: 120 }}
            value={riskTier}
            onChange={(v: string | undefined) => {
              setRiskTier(v)
              void load({ tier: v, page: 1 })
            }}
            options={[
              { label: '高风险', value: 'HIGH' },
              { label: '中风险', value: 'MEDIUM' },
              { label: '低风险', value: 'LOW' },
            ]}
          />
          <Select
            allowClear
            placeholder="当前负责人"
            style={{ width: 140 }}
            value={assigneeFilter}
            onChange={(v: number | undefined) => {
              setAssigneeFilter(v)
              void load({ assignee: v, page: 1 })
            }}
            options={collectors.map((c) => ({
              label: c.display_name,
              value: c.id,
            }))}
          />
          <Button type="primary" loading={assigning} onClick={onAutoAssign}>
            自动分配
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => load({ page: 1 })}>
            刷新
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={tasks}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          onChange: (p) => void load({ page: p }),
        }}
      />
    </Card>
  )
}
