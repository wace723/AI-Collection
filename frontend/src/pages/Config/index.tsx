import { useState, useEffect } from 'react'
import { Card, Upload, Alert, Table, message } from 'antd'
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
      message.success(`导入成功：新增 ${summary.inserted}，更新 ${summary.updated}，跳过 ${summary.skipped}`)
    } catch (err) {
      onError?.(err as Error)
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
      message.success(`已支付回写：更新 ${summary.updated}，跳过 ${summary.skipped}`)
    } catch (err) {
      onError?.(err as Error)
    } finally {
      setPaidLoading(false)
    }
  }

  const columns = [
    { title: '指标', dataIndex: 'label', key: 'label' },
    { title: '数量', dataIndex: 'value', key: 'value' },
  ]
  const pendingTableData = pendingResult
    ? [
        { key: 'inserted', label: '新增入库', value: pendingResult.inserted },
        { key: 'updated', label: '更新（重复）', value: pendingResult.updated },
        { key: 'skipped', label: '跳过', value: pendingResult.skipped },
        { key: 'errors', label: '错误行数', value: pendingResult.errors.length },
      ]
    : []
  const paidTableData = paidResult
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
            含风险概率列；新增订单入库+映射档位，重复订单更新风险概率/特征
          </p>
        </Dragger>

        {pendingResult && (
          <div style={{ marginTop: 24 }}>
            <Table
              columns={columns}
              dataSource={pendingTableData}
              pagination={false}
              size="small"
            />
            {pendingResult.errors.length > 0 && (
              <Alert
                style={{ marginTop: 12 }}
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
          </div>
        )}
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
            按服务费订单号匹配待支付订单，回写支付状态；无匹配跳过
          </p>
        </Dragger>

        {paidResult && (
          <div style={{ marginTop: 24 }}>
            <Table
              columns={columns}
              dataSource={paidTableData}
              pagination={false}
              size="small"
            />
            {paidResult.errors.length > 0 && (
              <Alert
                style={{ marginTop: 12 }}
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
          </div>
        )}
      </Card>

      <RiskConfigPanel />

      <AIConfigPanel />
    </>
  )
}
