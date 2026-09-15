import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Collapse,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import {
  claimTask,
  getMe,
  getTask,
  listTasks,
  submitTaskResult,
} from '../../api/tasks'
import { getRecommendTalks, generateTalk, sendFeedback } from '../../api/talk'
import type {
  GenerateTalk,
  Task,
  TaskDetail,
  TaskResultInput,
  TaskResultType,
  TaskStatus,
  TalkRecommend,
  User,
} from '../../types/api'

const { Text, Paragraph } = Typography

const PAGE_SIZE = 10

const statusOptions = [
  { label: '全部', value: '' },
  { label: '待处理', value: 'PENDING' },
  { label: '处理中', value: 'IN_PROGRESS' },
  { label: '已完成', value: 'DONE' },
  { label: '待分配', value: 'PENDING_ASSIGN' },
  { label: '已取消', value: 'CANCELLED' },
]

const resultOptions: { label: string; value: TaskResultType }[] = [
  { label: '已结清 (PAID)', value: 'PAID' },
  { label: '承诺还款 (PROMISE)', value: 'PROMISE' },
  { label: '异议 (DISPUTE)', value: 'DISPUTE' },
  { label: '失联 (LOST_CONTACT)', value: 'LOST_CONTACT' },
  { label: '其他 (OTHER)', value: 'OTHER' },
]

const riskColor: Record<string, string> = {
  HIGH: 'red',
  MEDIUM: 'orange',
  LOW: 'blue',
}
const statusColor: Record<string, string> = {
  PENDING_ASSIGN: 'default',
  PENDING: 'blue',
  IN_PROGRESS: 'gold',
  DONE: 'green',
  CANCELLED: 'default',
}
const statusLabel: Record<string, string> = {
  PENDING_ASSIGN: '待分配',
  PENDING: '待处理',
  IN_PROGRESS: '处理中',
  DONE: '已完成',
  CANCELLED: '已取消',
}
const sceneLabel = (s: string) =>
  (
    {
      FIRST: '首次',
      SECOND: '二次',
      THIRD: '三次',
      DISPUTE: '异议',
      PROMISE: '承诺',
    } as Record<string, string>
  )[s] ?? s

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
  const [talk, setTalk] = useState<TalkRecommend | null>(null)
  const [aiTalk, setAiTalk] = useState<GenerateTalk | null>(null)
  const [aiLoading, setAiLoading] = useState(false)

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

  const loadTalk = async (id: number) => {
    try {
      setTalk(await getRecommendTalks(id))
    } catch {
      setTalk(null)
    }
  }

  const refreshDetail = async (id: number) => {
    try {
      const d = await getTask(id)
      setDetail(d)
      await loadTalk(id)
    } catch {
      /* ignore */
    }
  }

  const onClaim = async (t: Task) => {
    try {
      await claimTask(t.id)
      message.success('已领取，请及时处理')
      fetchTasks(page, status)
      if (detailOpen && detail?.id === t.id) await refreshDetail(t.id)
    } catch {
      /* ignore */
    }
  }

  const openDetail = async (t: Task) => {
    setDetailOpen(true)
    setDetail(null)
    setTalk(null)
    setAiTalk(null)
    setDetailLoading(true)
    try {
      const d = await getTask(t.id)
      setDetail(d)
      await loadTalk(t.id)
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false)
    }
  }

  const onGenerateAi = async (taskId: number) => {
    setAiLoading(true)
    setAiTalk(null)
    try {
      const data = await generateTalk(taskId)
      setAiTalk(data)
      if (data.fallback) {
        message.warning(data.fallback_reason || 'AI 生成失败，已降级模板')
      } else {
        message.success('AI 话术已生成')
      }
    } catch {
      /* ignore */
    } finally {
      setAiLoading(false)
    }
  }

  const onFeedback = async (conversationId: number | null, fb: 'useful' | 'useless') => {
    if (!conversationId) return
    try {
      await sendFeedback(conversationId, fb)
      message.success(`已标记 ${fb}`)
    } catch {
      /* ignore */
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
    if (values.result === 'PROMISE' && values.next_followup_date) {
      payload.next_followup_date = dayjs(values.next_followup_date).format(
        'YYYY-MM-DD',
      )
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
    { title: '订单号', dataIndex: 'service_fee_order_no', width: 200 },
    { title: '供应商名称', dataIndex: 'supplier_name', width: 180 },
    {
      title: '风险档',
      dataIndex: 'risk_tier',
      width: 90,
      render: (v: string) => <Tag color={riskColor[v]}>{v}</Tag>,
    },
    {
      title: '场景',
      dataIndex: 'scene',
      width: 80,
      render: (v: string) => sceneLabel(v),
    },
    { title: '应催日', dataIndex: 'due_date', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={statusColor[v]}>{statusLabel[v] ?? v}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, t: Task) => (
        <Space>
          <Button size="small" onClick={() => openDetail(t)}>
            详情
          </Button>
          {t.status === 'PENDING' && (
            <Button size="small" type="primary" onClick={() => onClaim(t)}>
              领取
            </Button>
          )}
          {t.status === 'IN_PROGRESS' && (
            <Button size="small" type="primary" onClick={() => openResult(t)}>
              回填
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="催收工作台"
      extra={
        user ? (
          <Text type="secondary">
            {user.display_name}（{user.role}）
          </Text>
        ) : null
      }
    >
      <Space style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 160 }}
          value={status ?? ''}
          options={statusOptions}
          onChange={(v: string) =>
            fetchTasks(1, (v || undefined) as TaskStatus | undefined)
          }
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
      />

      <Drawer
        title="任务详情"
        open={detailOpen}
        width={560}
        onClose={() => setDetailOpen(false)}
        extra={
          detail ? (
            <Space>
              {detail.status === 'PENDING' && (
                <Button type="primary" onClick={() => onClaim(detail)}>
                  领取
                </Button>
              )}
              {detail.status === 'IN_PROGRESS' && (
                <Button type="primary" onClick={() => openResult(detail)}>
                  回填结果
                </Button>
              )}
            </Space>
          ) : null
        }
      >
        {detailLoading ? (
          <Spin />
        ) : detail ? (
          <>
            <Descriptions title="订单信息" column={2} bordered size="small">
              <Descriptions.Item label="订单号" span={2}>
                {detail.order?.service_fee_order_no}
              </Descriptions.Item>
              <Descriptions.Item label="供应商">
                {detail.order?.supplier_name}
              </Descriptions.Item>
              <Descriptions.Item label="中标日">
                {detail.order?.win_bid_date ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="支付状态">
                {detail.order?.pay_status ?? '未支付'}
              </Descriptions.Item>
              <Descriptions.Item label="风险概率">
                {detail.order?.risk_prob ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="注册地">
                {detail.order?.register_area ?? '-'}
              </Descriptions.Item>
            </Descriptions>

            <Descriptions
              title="任务信息"
              column={2}
              bordered
              size="small"
              style={{ marginTop: 16 }}
            >
              <Descriptions.Item label="风险档">
                <Tag color={riskColor[detail.risk_tier]}>
                  {detail.risk_tier}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="场景">
                {sceneLabel(detail.scene)}
              </Descriptions.Item>
              <Descriptions.Item label="应催日">
                {detail.due_date}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor[detail.status]}>
                  {statusLabel[detail.status] ?? detail.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="批次号">
                {detail.batch_id}
              </Descriptions.Item>
              <Descriptions.Item label="下次跟进">
                {detail.next_followup_date ?? '-'}
              </Descriptions.Item>
              {detail.result && (
                <Descriptions.Item label="处理结果" span={2}>
                  {detail.result}
                  {detail.result_note ? `（${detail.result_note}）` : ''}
                </Descriptions.Item>
              )}
            </Descriptions>

            {detail.feature && (
              <Descriptions
                title="用户特征画像"
                column={2}
                bordered
                size="small"
                style={{ marginTop: 16 }}
              >
                <Descriptions.Item label="历史平台使用费订单数">
                  {detail.feature.history_fee_order_count ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="历史缴费平均历时">
                  {detail.feature.avg_pay_duration_days ?? '-'} 天
                </Descriptions.Item>
                <Descriptions.Item label="历史中标率">
                  {detail.feature.win_rate ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="近90天活跃度">
                  {detail.feature.active_90d ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="中标时是否会员">
                  {detail.feature.is_member_at_win ? '是' : '否'}
                </Descriptions.Item>
                <Descriptions.Item label="注册资金">
                  {detail.feature.register_fund ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="供应商品类" span={2}>
                  {detail.feature.supplier_categories ?? '-'}
                </Descriptions.Item>
              </Descriptions>
            )}

            <Card
              title="推荐话术"
              size="small"
              style={{ marginTop: 16 }}
              extra={
                <Space>
                  {talk ? (
                    <Text type="secondary">
                      账龄段 {talk.age_bucket}
                      {talk.user_tag ? ` · ${talk.user_tag}` : ''}
                    </Text>
                  ) : null}
                  <Button
                    size="small"
                    loading={aiLoading}
                    onClick={() => onGenerateAi(detail.id)}
                  >
                    AI 生成
                  </Button>
                </Space>
              }
            >
              {talk && talk.templates.length > 0 ? (
                <>
                  <Paragraph style={{ marginBottom: 8 }}>
                    {talk.templates[0].content}
                  </Paragraph>
                  {talk.templates.length > 1 && (
                    <Collapse
                      size="small"
                      items={[
                        {
                          key: 'more',
                          label: `其他候选话术（${talk.templates.length - 1}）`,
                          children: talk
                            .templates!.slice(1)
                            .map((tp) => (
                              <Paragraph key={tp.template_id} style={{ marginBottom: 4 }}>
                                {tp.content}
                              </Paragraph>
                            )),
                        },
                      ]}
                    />
                  )}
                </>
              ) : (
                <Text type="secondary">暂无匹配话术模板</Text>
              )}

              {aiTalk && (
                <div style={{ marginTop: 12, borderTop: '1px dashed #ddd', paddingTop: 8 }}>
                  <Space style={{ marginBottom: 4 }}>
                    <Tag color={aiTalk.fallback ? 'orange' : 'green'}>
                      AI{aiTalk.fallback ? '（降级）' : ''}
                    </Tag>
                    <Text type="secondary">{aiTalk.provider}</Text>
                    {aiTalk.conversation_id && (
                      <>
                        <Button
                          size="small"
                          type="link"
                          onClick={() => onFeedback(aiTalk.conversation_id, 'useful')}
                        >
                          有用
                        </Button>
                        <Button
                          size="small"
                          type="link"
                          onClick={() => onFeedback(aiTalk.conversation_id, 'useless')}
                        >
                          无用
                        </Button>
                      </>
                    )}
                  </Space>
                  <Paragraph style={{ marginBottom: 0 }}>
                    {aiTalk.content || '（无内容）'}
                  </Paragraph>
                </div>
              )}
            </Card>
          </>
        ) : null}
      </Drawer>

      <Modal
        title="回填处理结果"
        open={resultOpen}
        confirmLoading={submitting}
        onOk={onSubmitResult}
        onCancel={() => setResultOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="处理结果"
            name="result"
            rules={[{ required: true, message: '请选择处理结果' }]}
          >
            <Select options={resultOptions} placeholder="选择处理结果" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.result !== cur.result}>
            {({ getFieldValue }) =>
              getFieldValue('result') === 'PROMISE' ? (
                <Form.Item
                  label="承诺还款日"
                  name="next_followup_date"
                  rules={[{ required: true, message: '承诺还款需选择日期' }]}
                >
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item label="备注" name="note">
            <Input.TextArea rows={3} placeholder="处理说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
