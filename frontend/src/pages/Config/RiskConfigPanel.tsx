import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  InputNumber,
  Select,
  Space,
  Popconfirm,
  Tag,
  Descriptions,
  message,
} from 'antd'
import { PlusOutlined, MinusCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getRiskConfig,
  updateRiskConfig,
  getRiskHistory,
  rollbackRisk,
} from '../../api/config'
import type {
  RiskConfig,
  RiskTier,
  Scene,
  CollectionSchedule,
} from '../../types/api'

const RISK_TIER_OPTIONS: { label: string; value: RiskTier }[] = [
  { label: '高风险', value: 'HIGH' },
  { label: '中风险', value: 'MEDIUM' },
  { label: '低风险', value: 'LOW' },
]

const SCENE_OPTIONS: { label: string; value: Scene }[] = [
  { label: '第1轮', value: 'ROUND_1' },
  { label: '第2轮', value: 'ROUND_2' },
  { label: '第3轮', value: 'ROUND_3' },
  { label: '第4轮', value: 'ROUND_4' },
  { label: '第5轮', value: 'ROUND_5' },
]

const TIER_COLOR: Record<RiskTier, string> = {
  HIGH: 'red',
  MEDIUM: 'orange',
  LOW: 'green',
}

/** 默认催收时点（与后端 DEFAULT_SCHEDULES 一致） */
const DEFAULT_SCHEDULES: CollectionSchedule[] = [
  { risk_tier: 'HIGH', day_offset: 7, scene: 'ROUND_1', seq: 1, is_active: true },
  { risk_tier: 'HIGH', day_offset: 15, scene: 'ROUND_2', seq: 2, is_active: true },
  { risk_tier: 'HIGH', day_offset: 30, scene: 'ROUND_3', seq: 3, is_active: true },
  { risk_tier: 'MEDIUM', day_offset: 30, scene: 'ROUND_1', seq: 1, is_active: true },
  { risk_tier: 'LOW', day_offset: 90, scene: 'ROUND_1', seq: 1, is_active: true },
]

const scheduleColumns: ColumnsType<CollectionSchedule> = [
  {
    title: '风险档',
    dataIndex: 'risk_tier',
    key: 'risk_tier',
    render: (t: RiskTier) => <Tag color={TIER_COLOR[t]}>{t}</Tag>,
  },
  { title: '第N天', dataIndex: 'day_offset', key: 'day_offset' },
  { title: '场景', dataIndex: 'scene', key: 'scene' },
  { title: '轮次', dataIndex: 'seq', key: 'seq' },
]

export default function RiskConfigPanel() {
  const [current, setCurrent] = useState<RiskConfig | null>(null)
  const [history, setHistory] = useState<RiskConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [cur, hist] = await Promise.all([
        getRiskConfig(),
        getRiskHistory(),
      ])
      setCurrent(cur)
      setHistory(hist)
    } catch {
      // client 拦截器已统一提示
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const openEdit = () => {
    // 用当前配置初始化表单；若无当前配置则用默认值
    const base = current ?? {
      high_threshold: 70,
      medium_threshold: 30,
      schedules: DEFAULT_SCHEDULES,
    }
    form.setFieldsValue({
      high_threshold: base.high_threshold,
      medium_threshold: base.medium_threshold,
      schedules: base.schedules.map((s) => ({ ...s })),
    })
    setEditOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      // 前端二次校验 high > medium > 0
      if (values.high_threshold <= values.medium_threshold) {
        message.error('高风险阈值必须严格大于中风险阈值')
        return
      }
      setSubmitting(true)
      const payload = {
        high_threshold: Number(values.high_threshold),
        medium_threshold: Number(values.medium_threshold),
        schedules: (values.schedules as CollectionSchedule[]).map((s) => ({
          risk_tier: s.risk_tier,
          day_offset: Number(s.day_offset),
          scene: s.scene,
          seq: Number(s.seq),
          is_active: true,
        })),
      }
      await updateRiskConfig(payload).then((cfg) => {
        message.success('配置已更新，生成新版本')
        // talk-003：风险档变更后附加话术覆盖度提示（不阻断）
        const hint = cfg.coverage_hint
        if (hint) {
          const parts: string[] = []
          if (hint.added_rounds?.length) {
            parts.push(`新增轮次 ${hint.added_rounds.map((r) => `${r.risk_tier} ${r.scene}`).join('、')} 建议补充话术`)
          }
          if (hint.deleted_rounds?.length) {
            parts.push(`删除轮次 ${hint.deleted_rounds.map((r) => `${r.risk_tier} ${r.scene}`).join('、')} 话术已成孤儿，建议清理`)
          }
          if (hint.missing_cells?.length) {
            parts.push(`当前共 ${hint.missing_cells.length} 格话术缺口，建议在「话术配置」面板补全`)
          }
          if (parts.length) {
            message.warning(parts.join('；'), 6)
          }
        }
      })
      setEditOpen(false)
      refresh()
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleRollback = async (version: number) => {
    try {
      await rollbackRisk(version)
      message.success(`已回滚到版本 ${version} 的配置值`)
      refresh()
    } catch {
      // client 拦截器已统一提示
    }
  }

  const historyColumns: ColumnsType<RiskConfig> = [
    { title: '版本', dataIndex: 'version', key: 'version', width: 80 },
    {
      title: '高风险阈值',
      dataIndex: 'high_threshold',
      key: 'high_threshold',
      width: 120,
    },
    {
      title: '中风险阈值',
      dataIndex: 'medium_threshold',
      key: 'medium_threshold',
      width: 120,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 90,
      render: (active: boolean) =>
        active ? <Tag color="blue">生效中</Tag> : <Tag>历史</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: RiskConfig) =>
        record.is_active ? (
          <span style={{ color: '#999' }}>—</span>
        ) : (
          <Popconfirm
            title={`回滚到版本 ${record.version}？`}
            description="将复制该版本配置为新版本生效"
            onConfirm={() => handleRollback(record.version)}
            okText="回滚"
            cancelText="取消"
          >
            <Button size="small">回滚</Button>
          </Popconfirm>
        ),
    },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      {/* 当前生效配置 */}
      <Card
        title="风险档配置 — 当前生效"
        loading={loading && !current}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
              刷新
            </Button>
            <Button type="primary" onClick={openEdit} disabled={!current}>
              编辑配置
            </Button>
          </Space>
        }
      >
        {current ? (
          <>
            <Descriptions column={4} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="版本">
                v{current.version}
              </Descriptions.Item>
              <Descriptions.Item label="高风险阈值">
                {current.high_threshold}
              </Descriptions.Item>
              <Descriptions.Item label="中风险阈值">
                {current.medium_threshold}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {new Date(current.updated_at).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey={(r) => `${r.risk_tier}-${r.day_offset}`}
              columns={scheduleColumns}
              dataSource={current.schedules}
              pagination={false}
            />
          </>
        ) : (
          <span style={{ color: '#999' }}>暂无生效配置，请运行 seed 初始化</span>
        )}
      </Card>

      {/* 配置历史 */}
      <Card title="配置历史" loading={loading && history.length === 0}>
        <Table
          size="small"
          rowKey="version"
          columns={historyColumns}
          dataSource={history}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑风险档配置"
        open={editOpen}
        onOk={handleSubmit}
        onCancel={() => setEditOpen(false)}
        confirmLoading={submitting}
        okText="保存（生成新版本）"
        cancelText="取消"
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Space style={{ width: '100%' }} size="large">
            <Form.Item
              name="high_threshold"
              label="高风险阈值（≥ 此值为高风险）"
              rules={[
                { required: true, message: '请输入' },
                {
                  validator: (_, v) =>
                    v > 0 && v < 100
                      ? Promise.resolve()
                      : Promise.reject(new Error('阈值须在 0~100 之间')),
                },
              ]}
            >
              <InputNumber min={0} max={100} step={0.01} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item
              name="medium_threshold"
              label="中风险阈值（≥ 此值为中风险）"
              rules={[
                { required: true, message: '请输入' },
                {
                  validator: (_, v) =>
                    v > 0 && v < 100
                      ? Promise.resolve()
                      : Promise.reject(new Error('阈值须在 0~100 之间')),
                },
              ]}
            >
              <InputNumber min={0} max={100} step={0.01} style={{ width: 160 }} />
            </Form.Item>
          </Space>

          <Form.Item style={{ marginBottom: 8 }}>
            <Space>
              <span style={{ fontWeight: 500 }}>催收时点</span>
              <Button
                size="small"
                onClick={() =>
                  form.setFieldValue('schedules', DEFAULT_SCHEDULES)
                }
              >
                恢复默认时点
              </Button>
            </Space>
          </Form.Item>

          <Form.List name="schedules">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name }) => (
                  <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item
                      name={[name, 'risk_tier']}
                      rules={[{ required: true, message: '选档' }]}
                    >
                      <Select
                        options={RISK_TIER_OPTIONS}
                        style={{ width: 110 }}
                        placeholder="风险档"
                      />
                    </Form.Item>
                    <Form.Item
                      name={[name, 'day_offset']}
                      rules={[
                        { required: true, message: '输入' },
                        {
                          validator: (_, v) =>
                            Number.isInteger(v) && v > 0
                              ? Promise.resolve()
                              : Promise.reject(new Error('正整数')),
                        },
                      ]}
                    >
                      <InputNumber min={1} style={{ width: 90 }} placeholder="第N天" />
                    </Form.Item>
                    <Form.Item
                      name={[name, 'scene']}
                      rules={[{ required: true, message: '选场景' }]}
                    >
                      <Select
                        options={SCENE_OPTIONS}
                        style={{ width: 110 }}
                        placeholder="场景"
                      />
                    </Form.Item>
                    <Form.Item
                      name={[name, 'seq']}
                      rules={[
                        { required: true, message: '输入' },
                        {
                          validator: (_, v) =>
                            Number.isInteger(v) && v >= 1
                              ? Promise.resolve()
                              : Promise.reject(new Error('≥1')),
                        },
                      ]}
                    >
                      <InputNumber min={1} style={{ width: 80 }} placeholder="轮次" />
                    </Form.Item>
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ color: '#999' }}
                    />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() =>
                    add({
                      risk_tier: 'HIGH',
                      day_offset: 7,
                      scene: 'ROUND_1',
                      seq: 1,
                      is_active: true,
                    })
                  }
                  icon={<PlusOutlined />}
                  style={{ width: 200 }}
                >
                  添加催收时点
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </Space>
  )
}
