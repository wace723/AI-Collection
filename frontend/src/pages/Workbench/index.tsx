import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  getMe,
  getTask,
  listTasks,
  submitTaskResult,
} from '../../api/tasks'
import type {
  Task,
  TaskDetail,
  TaskResultInput,
  TaskResultType,
  TaskStatus,
  User,
} from '../../types/api'
import TaskDetailModal from './TaskDetailModal'

const { Text } = Typography

const PAGE_SIZE = 10

const statusOptions = [
  { label: '全部', value: '' },
  { label: '待分配', value: 'PENDING_ASSIGN' },
  { label: '处理中', value: 'IN_PROGRESS' },
  { label: '已完成', value: 'DONE' },
  { label: '已取消', value: 'CANCELLED' },
]

const resultOptions: { label: string; value: TaskResultType }[] = [
  { label: '已接通 (REACHED)', value: 'REACHED' },
  { label: '未接通 (UNREACHED)', value: 'UNREACHED' },
]

const collectionStateLabel: Record<string, string> = {
  NO_NEED: '无需催收',
  PENDING_COLLECTION: '待催收',
  COLLECTED: '已催收',
  FINALIZED: '终态',
}
const collectionStateColor: Record<string, string> = {
  NO_NEED: 'default',
  PENDING_COLLECTION: 'gold',
  COLLECTED: 'green',
  FINALIZED: 'default',
}

const riskColor: Record<string, string> = { HIGH: 'red', MEDIUM: 'orange', LOW: 'blue' }
const statusColor: Record<string, string> = {
  PENDING_ASSIGN: 'default', IN_PROGRESS: 'gold',
  DONE: 'green', CANCELLED: 'default',
}
const statusLabel: Record<string, string> = {
  PENDING_ASSIGN: '待分配', IN_PROGRESS: '处理中',
  DONE: '已完成', CANCELLED: '已取消',
}
const sceneLabel = (s: string) =>
  ({ FIRST: '首次', SECOND: '二次', THIRD: '三次' } as Record<string, string>)[s] ?? s

export default function Workbench() {
  const [user, setUser] = useState<User | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<TaskStatus | undefined>(undefined)
  const [loading, setLoading] = useState(false)

  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [resultOpen, setResultOpen] = useState(false)
  const [resultTask, setResultTask] = useState<Task | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const fetchTasks = useCallback(
    async (p: number, st?: TaskStatus) => {
      setLoading(true)
      try {
        const data = await listTasks({ page: p, size: PAGE_SIZE, status: st })
        setTasks(data.items)
        setTotal(data.total)
        setPage(p)
        setStatus(st)
      } catch {
        /* client 拦截器已统一提示 */
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    getMe().then(setUser).catch(() => {})
    fetchTasks(1, undefined)
  }, [fetchTasks])

  const refreshDetail = async (id: number) => {
    try {
      const d = await getTask(id)
      setDetail(d)
    } catch {
      /* ignore */
    }
  }

  const openDetail = async (t: Task) => {
    setDetailOpen(true)
    setDetail(null)
    setDetailLoading(true)
    try {
      const d = await getTask(t.id)
      setDetail(d)
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false)
    }
  }

  const openResult = (t: Task) => {
    setResultTask(t)
    form.resetFields()
    setResultOpen(true)
  }

  const onSubmitResult = async () => {
    if (!resultTask) return
    const values = await form.validateFields()
    const payload: TaskResultInput = {
      result: values.result as TaskResultType,
      note: values.note,
    }
    setSubmitting(true)
    try {
      await submitTaskResult(resultTask.id, payload)
      message.success('结果已回填')
      setResultOpen(false)
      fetchTasks(page, status)
      if (detailOpen && detail?.id === resultTask.id)
        await refreshDetail(resultTask.id)
    } catch {
      /* ignore */
    } finally {
      setSubmitting(false)
    }
  }

  const columns: ColumnsType<Task> = [
    { title: '服务费订单号', dataIndex: 'service_fee_order_no', width: 200 },
    { title: '标的名称', dataIndex: 'subject_name', width: 180, ellipsis: true,
      render: (v: string | null) => v ?? '-' },
    { title: '供应商名称', dataIndex: 'supplier_name', width: 180, ellipsis: true },
    { title: '概算金额', dataIndex: 'subject_estimate_amount', width: 120,
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-') },
    { title: '中标日期', dataIndex: 'win_bid_date', width: 120,
      render: (v: string | null) => v ?? '-' },
    {
      title: '风险档', dataIndex: 'risk_tier', width: 90,
      render: (v: string) => <Tag color={riskColor[v]}>{v}</Tag>,
    },
    { title: '场景', dataIndex: 'scene', width: 80, render: (v: string) => sceneLabel(v) },
    { title: '应催日', dataIndex: 'due_date', width: 120 },
    {
      title: '催收状态', dataIndex: 'collection_state', width: 100,
      render: (v: string) => (
        <Tag color={collectionStateColor[v] ?? 'default'}>
          {collectionStateLabel[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => <Tag color={statusColor[v]}>{statusLabel[v] ?? v}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: unknown, t: Task) => (
        <Space>
          <Button size="small" onClick={() => openDetail(t)}>详情</Button>
          {t.status === 'IN_PROGRESS' && (
            <Button size="small" type="primary" onClick={() => openResult(t)}>回填</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="催收工作台"
      extra={user ? <Text type="secondary">{user.display_name}（{user.role}）</Text> : null}
    >
      <Space style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 160 }}
          value={status ?? ''}
          options={statusOptions}
          onChange={(v: string) => fetchTasks(1, (v || undefined) as TaskStatus | undefined)}
        />
        <Button onClick={() => fetchTasks(page, status)}>刷新</Button>
        <Text type="secondary">共 {total} 条</Text>
      </Space>

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
          onChange: (p) => fetchTasks(p, status),
        }}
        scroll={{ x: 1300 }}
      />

      <TaskDetailModal
        open={detailOpen}
        detail={detail}
        loading={detailLoading}
        onClose={() => setDetailOpen(false)}
        onResult={detail ? () => openResult(detail) : undefined}
      />

      <Modal
        title="回填处理结果"
        open={resultOpen}
        confirmLoading={submitting}
        onOk={onSubmitResult}
        onCancel={() => setResultOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item label="处理结果" name="result" rules={[{ required: true, message: '请选择处理结果' }]}>
            <Select options={resultOptions} placeholder="选择处理结果" />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.result !== cur.result}
          >
            {({ getFieldValue }) =>
              getFieldValue('result') === 'REACHED' ? (
                <Form.Item
                  label="反馈内容"
                  name="note"
                  rules={[{ required: true, message: '已接通需填写反馈内容' }]}
                >
                  <Input.TextArea rows={3} placeholder="填写与客户的沟通情况" />
                </Form.Item>
              ) : (
                <Form.Item label="备注" name="note">
                  <Input.TextArea rows={3} placeholder="处理说明（可选）" />
                </Form.Item>
              )
            }
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
