import { useEffect, useState } from 'react'
import { Button, Card, Collapse, Descriptions, Modal, Space, Spin, Tag, Typography, message } from 'antd'
import { getRecommendTalks, generateTalk, sendFeedback } from '../../api/talk'
import type { GenerateTalk, TaskDetail, TalkRecommend } from '../../types/api'

const { Text, Paragraph } = Typography

interface Props {
  open: boolean
  detail: TaskDetail | null
  loading: boolean
  onClose: () => void
  onResult?: () => void
}

const riskColor: Record<string, string> = { HIGH: 'red', MEDIUM: 'orange', LOW: 'blue' }
const statusLabel: Record<string, string> = {
  PENDING_ASSIGN: '待分配', IN_PROGRESS: '处理中',
  DONE: '已完成', CANCELLED: '已取消',
}
const sceneLabel = (s: string) =>
  ({ FIRST: '首次', SECOND: '二次', THIRD: '三次' } as Record<string, string>)[s] ?? s

const collectionStateLabel: Record<string, string> = {
  NO_NEED: '无需催收',
  PENDING_COLLECTION: '待催收',
  COLLECTED: '已催收',
  FINALIZED: '终态',
}

/** 任务详情 Modal：左右两栏（左=订单/任务/特征，右=模板话术+AI话术） */
export default function TaskDetailModal({ open, detail, loading, onClose, onResult }: Props) {
  return (
    <Modal
      title="任务详情"
      open={open}
      onCancel={onClose}
      width={1100}
      footer={null}
      destroyOnClose
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : detail ? (
        <div style={{ display: 'flex', gap: 16 }}>
          <LeftPanel detail={detail} />
          <RightPanel detail={detail} onResult={onResult} />
        </div>
      ) : null}
    </Modal>
  )
}

/** 左栏：订单信息 + 任务信息 + 特征画像（分类） */
function LeftPanel({ detail }: { detail: TaskDetail }) {
  const o = detail.order
  const f = detail.feature
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {o && (
        <Descriptions title="订单信息" column={2} bordered size="small">
          <Descriptions.Item label="服务费订单号" span={2}>{o.service_fee_order_no}</Descriptions.Item>
          <Descriptions.Item label="标的名称" span={2}>{o.subject_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="供应商">{o.supplier_name}</Descriptions.Item>
          <Descriptions.Item label="供应商编号">{o.supplier_no}</Descriptions.Item>
          <Descriptions.Item label="招标编号">{o.biz_no}</Descriptions.Item>
          <Descriptions.Item label="标的概算金额">{o.subject_estimate_amount ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="中标日期">{o.win_bid_date ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="订单生成日期">{o.order_generated_date ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="招标类型">{o.tender_type_desc ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="采购类型">{o.purchase_type_desc ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="中标品类">{o.bid_category ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="合同类型">{o.contract_type ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="注册地">{o.register_area ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="注册省份">{o.register_province ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="支付状态">{o.pay_status ?? '未支付'}</Descriptions.Item>
          <Descriptions.Item label="支付时间">{o.pay_time ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="实际支付时长">{o.actual_pay_duration_days != null ? `${o.actual_pay_duration_days} 天` : '-'}</Descriptions.Item>
          <Descriptions.Item label="风险概率">{o.risk_prob ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="风险档"><Tag color={riskColor[o.risk_tier ?? '']}>{o.risk_tier ?? '-'}</Tag></Descriptions.Item>
        </Descriptions>
      )}

      <Descriptions title="任务信息" column={2} bordered size="small" style={{ marginTop: 16 }}>
        <Descriptions.Item label="风险档"><Tag color={riskColor[detail.risk_tier]}>{detail.risk_tier}</Tag></Descriptions.Item>
        <Descriptions.Item label="场景">{sceneLabel(detail.scene)}</Descriptions.Item>
        <Descriptions.Item label="应催日">{detail.due_date}</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag>{statusLabel[detail.status] ?? detail.status}</Tag></Descriptions.Item>
        <Descriptions.Item label="批次号">{detail.batch_id}</Descriptions.Item>
        <Descriptions.Item label="催收状态">
          <Tag>{collectionStateLabel[detail.collection_state] ?? detail.collection_state}</Tag>
        </Descriptions.Item>
        {detail.result && (
          <Descriptions.Item label="处理结果" span={2}>{detail.result}{detail.result_note ? `（${detail.result_note}）` : ''}</Descriptions.Item>
        )}
      </Descriptions>

      {f && (
        <>
          <Descriptions title="A 类 · 缴费历史" column={3} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="历史平台使用费订单数">{f.history_fee_order_count ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="上次缴费历时">{f.last_pay_duration_days ? `${f.last_pay_duration_days} 天` : '-'}</Descriptions.Item>
            <Descriptions.Item label="历史平均历时">{f.avg_pay_duration_days ? `${f.avg_pay_duration_days} 天` : '-'}</Descriptions.Item>
          </Descriptions>
          <Descriptions title="B 类 · 活跃度与支付" column={3} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="历史支付金额">{f.fwsc_history_pay_amount ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="历史报名次数">{f.signup_count ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="历史投标次数">{f.bidding_count ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="历史中标次数">{f.win_count ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="历史中标率">{f.win_rate ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="近90天活跃度">{f.active_90d ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="首次中标间隔">{f.first_win_interval_days ? `${f.first_win_interval_days} 天` : '-'}</Descriptions.Item>
            <Descriptions.Item label="中标时会员">{f.is_member_at_win ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="中标前购会员次数">{f.member_purchase_count_before_win ?? '-'}</Descriptions.Item>
          </Descriptions>
          <Descriptions title="C 类 · 资质与标签" column={3} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="注册资金">{f.register_fund ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="注册距中标间隔">{f.register_interval_days ? `${f.register_interval_days} 天` : '-'}</Descriptions.Item>
            <Descriptions.Item label="入驻距中标间隔">{f.in_date_interval_days ? `${f.in_date_interval_days} 天` : '-'}</Descriptions.Item>
            <Descriptions.Item label="最早入库距中标">{f.entry_interval_days ? `${f.entry_interval_days} 天` : '-'}</Descriptions.Item>
            <Descriptions.Item label="供应商品类" span={2}>{f.supplier_categories ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="标签表中标率">{f.ads_win_rate ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="优质评级次数">{f.high_quality_cnt ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="合作单位数">{f.cooperate_org_num ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="累计履约项目">{f.total_perform_project_num ?? '-'}</Descriptions.Item>
          </Descriptions>
        </>
      )}
    </div>
  )
}

/** 右栏：上=模板话术（默认有），下=AI生成话术（点击生成后有） */
function RightPanel({ detail, onResult }: { detail: TaskDetail; onResult?: () => void }) {
  return (
    <div style={{ width: 360, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <TemplateTalkCard taskId={detail.id} />
      <AiTalkCard taskId={detail.id} />
      {onResult && (detail.status === 'PENDING' || detail.status === 'IN_PROGRESS') && (
        <Button type="primary" block onClick={onResult}>回填结果</Button>
      )}
    </div>
  )
}

/** 模板话术（默认加载） */
function TemplateTalkCard({ taskId }: { taskId: number }) {
  const [talk, setTalk] = useState<TalkRecommend | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    getRecommendTalks(taskId)
      .then((d) => { if (active) setTalk(d) })
      .catch(() => { if (active) setTalk(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [taskId])

  return (
    <Card title="模板话术" size="small" extra={talk ? <Text type="secondary">账龄 {talk.age_bucket}</Text> : null}>
      {loading ? <Spin /> : talk && talk.templates.length > 0 ? (
        <>
          <Paragraph style={{ marginBottom: 8 }}>{talk.templates[0].content}</Paragraph>
          {talk.templates.length > 1 && (
            <Collapse
              size="small"
              items={[{
                key: 'more',
                label: `其他候选（${talk.templates.length - 1}）`,
                children: talk.templates.slice(1).map((tp) => (
                  <Paragraph key={tp.template_id} style={{ marginBottom: 4 }}>{tp.content}</Paragraph>
                )),
              }]}
            />
          )}
        </>
      ) : <Text type="secondary">暂无匹配模板</Text>}
    </Card>
  )
}

/** AI 生成话术（点击生成后有） */
function AiTalkCard({ taskId }: { taskId: number }) {
  const [aiTalk, setAiTalk] = useState<GenerateTalk | null>(null)
  const [aiLoading, setAiLoading] = useState(false)

  const onGenerate = async () => {
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

  const onFeedback = async (conversationId: number, fb: 'useful' | 'useless') => {
    try {
      await sendFeedback(conversationId, fb)
      message.success(`已标记 ${fb}`)
    } catch {
      /* ignore */
    }
  }

  return (
    <Card
      title="AI 话术"
      size="small"
      extra={<Button size="small" loading={aiLoading} onClick={onGenerate}>{aiLoading ? '生成中…' : '生成'}</Button>}
    >
      {aiTalk ? (
        <>
          <Space style={{ marginBottom: 4 }}>
            <Tag color={aiTalk.fallback ? 'orange' : 'green'}>AI{aiTalk.fallback ? '（降级）' : ''}</Tag>
            <Text type="secondary">{aiTalk.provider}</Text>
            {aiTalk.conversation_id && (
              <>
                <Button size="small" type="link" onClick={() => onFeedback(aiTalk.conversation_id!, 'useful')}>有用</Button>
                <Button size="small" type="link" onClick={() => onFeedback(aiTalk.conversation_id!, 'useless')}>无用</Button>
              </>
            )}
          </Space>
          <Paragraph style={{ marginBottom: 0 }}>{aiTalk.content || '（无内容）'}</Paragraph>
        </>
      ) : (
        <Text type="secondary">点击「生成」获取 AI 话术</Text>
      )}
    </Card>
  )
}
