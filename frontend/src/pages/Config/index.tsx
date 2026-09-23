import { useState, useEffect } from 'react'
import { Card, Upload, Alert, Modal, Statistic, Row, Col, Table, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadRequestOption } from 'rc-upload/lib/interface'
import { uploadPendingCsv, uploadPaidCsv } from '../../api/data'
import { getMe } from '../../api/auth'
import type { UploadSummary } from '../../types/api'
import RiskConfigPanel from './RiskConfigPanel'
import AIConfigPanel from './AIConfigPanel'

const { Dragger } = Upload

/** 配置后台：CSV 导入（待支付/已支付）+ 风险档配置 + AI 配置 */
export default function Config() {
  const [pendingResult, setPendingResult] = useState<UploadSummary | null>(null)
  const [paidResult, setPaidResult] = useState<UploadSummary | null>(null)
  const [pendingLoading, setPendingLoading] = useState(false)
  const [paidLoading, setPaidLoading] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [userLoaded, setUserLoaded] = useState(false)

  useEffect(() => {
    getMe()
      .then((u) => setIsAdmin(u.role === 'ADMIN'))
      .finally(() => setUserLoaded(true))
  }, [])

  const handlePendingUpload = async (option: UploadRequestOption) => {
    const { file, onSuccess, onError } = option
    setPendingLoading(true)
    try {
      const summary = await uploadPendingCsv(file as File)
      setPendingResult(summary)
      onSuccess?.({}, file)
      message.success('导入完成，已自动跑批生成任务')
    } catch (err) {
      onError?.(err as Error)
      message.error('导入失败（请检查 CSV 格式或网络/超时）')
    } finally {
      setPendingLoading(false)
    }
  }

  const handlePaidUpload = async (option: UploadRequestOption) => {
    const { file, onSuccess, onError } = option
    setPaidLoading(true)
    try {
      const summary = await uploadPaidCsv(file as File)
      setPaidResult(summary)
      onSuccess?.({}, file)
      message.success('已支付回写完成')
    } catch (err) {
      onError?.(err as Error)
      message.error('导入失败（请检查 CSV 格式或网络/超时）')
    } finally {
      setPaidLoading(false)
    }
  }

  const statColumns = [
    { title: '指标', dataIndex: 'label', key: 'label' },
    { title: '数量', dataIndex: 'value', key: 'value' },
  ]
  const pendingStatData = pendingResult
    ? [
        { key: 'inserted', label: '新增入库', value: pendingResult.inserted },
        { key: 'updated', label: '更新（重复）', value: pendingResult.updated },
        { key: 'skipped', label: '跳过', value: pendingResult.skipped },
        { key: 'errors', label: '错误行数', value: pendingResult.errors.length },
      ]
    : []
  const paidStatData = paidResult
    ? [
        { key: 'updated', label: '回写支付状态', value: paidResult.updated },
        { key: 'skipped', label: '跳过（无匹配/已支付）', value: paidResult.skipped },
        { key: 'errors', label: '错误行数', value: paidResult.errors.length },
      ]
    : []

  if (!userLoaded) {
    return <Card title="配置后台" loading />
  }

  if (!isAdmin) {
    return (
      <Card title="配置后台">
        <Alert
          type="warning"
          message="权限不足"
          description="配置后台仅管理员可操作。"
          showIcon
        />
      </Card>
    )
  }

  return (
    <>
      <Card title="待支付订单导入 — CSV（全量/增量）" style={{ marginBottom: 24 }}>
        <Dragger
          accept=".csv"
          multiple={false}
          showUploadList={false}
          customRequest={handlePendingUpload}
          disabled={pendingLoading}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽待支付订单 CSV 到此处上传</p>
          <p className="ant-upload-hint">
            40 列（含工程局单位/下属单位/风险概率）；导入后自动跑批生成任务
          </p>
        </Dragger>
      </Card>

      <Card title="已支付订单导入 — CSV（回写支付状态）" style={{ marginBottom: 24 }}>
        <Dragger
          accept=".csv"
          multiple={false}
          showUploadList={false}
          customRequest={handlePaidUpload}
          disabled={paidLoading}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽已支付订单 CSV 到此处上传</p>
          <p className="ant-upload-hint">
            40 列；按服务费订单号匹配待支付订单，回写支付状态+终态停催；无匹配跳过
          </p>
        </Dragger>
      </Card>

      {/* 待支付导入结果 Modal */}
      <Modal
        title="待支付导入结果"
        open={pendingResult !== null}
        onCancel={() => setPendingResult(null)}
        footer={null}
        width={640}
        destroyOnClose
      >
        {pendingResult && (
          <>
            <Table
              columns={statColumns}
              dataSource={pendingStatData}
              pagination={false}
              size="small"
              style={{ marginBottom: 16 }}
            />
            {pendingResult.batch_result && (
              <>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={8}>
                    <Statistic
                      title="跑批生成任务"
                      value={pendingResult.batch_result.generated}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="跨区间删旧任务"
                      value={pendingResult.batch_result.deleted}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="风险档分布"
                      value={Object.entries(pendingResult.batch_result.by_tier)
                        .map(([k, v]) => `${k}:${v}`)
                        .join(' / ') || '无'}
                    />
                  </Col>
                </Row>
                <Alert
                  type="info"
                  message="导入后已自动跑批"
                  description="跑批推进订单催收状态机并生成当轮催收任务，可在工作台查看。"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              </>
            )}
            {pendingResult.errors.length > 0 && (
              <Alert
                type="error"
                message="部分行解析失败"
                description={
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {pendingResult.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                }
                showIcon
              />
            )}
          </>
        )}
      </Modal>

      {/* 已支付导入结果 Modal */}
      <Modal
        title="已支付导入结果"
        open={paidResult !== null}
        onCancel={() => setPaidResult(null)}
        footer={null}
        width={560}
        destroyOnClose
      >
        {paidResult && (
          <>
            <Table
              columns={statColumns}
              dataSource={paidStatData}
              pagination={false}
              size="small"
              style={{ marginBottom: 16 }}
            />
            <Alert
              type="info"
              message="已支付回写"
              description="匹配到的订单已回写支付状态并停催（collection_state→终态，未完成任务已取消）。"
              showIcon
              style={{ marginBottom: 16 }}
            />
            {paidResult.errors.length > 0 && (
              <Alert
                type="warning"
                message="部分行提示"
                description={
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {paidResult.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                }
                showIcon
              />
            )}
          </>
        )}
      </Modal>

      <RiskConfigPanel />

      <AIConfigPanel />
    </>
  )
}
