import { useState, useEffect } from 'react'
import { Card, Upload, Alert, Table, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadRequestOption } from 'rc-upload/lib/interface'
import { uploadCsv } from '../../api/data'
import { getMe } from '../../api/auth'
import type { UploadSummary } from '../../types/api'

const { Dragger } = Upload

/** CSV 上传区 + 最近上传结果 */
export default function Config() {
  const [result, setResult] = useState<UploadSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [userLoaded, setUserLoaded] = useState(false)

  useEffect(() => {
    getMe()
      .then((u) => setIsAdmin(u.role === 'ADMIN'))
      .finally(() => setUserLoaded(true))
  }, [])

  const handleUpload = async (option: UploadRequestOption) => {
    const { file, onSuccess, onError } = option
    setLoading(true)
    try {
      const summary = await uploadCsv(file as File)
      setResult(summary)
      onSuccess?.({}, file)
      message.success(`上传成功：新增 ${summary.inserted} 条，跳过 ${summary.skipped} 条`)
    } catch (err) {
      onError?.(err as Error)
    } finally {
      setLoading(false)
    }
  }

  // 仅作上传结果摘要展示（非完整订单表，订单表留给 wb-001 工作台）
  const columns = [
    { title: '指标', dataIndex: 'label', key: 'label' },
    { title: '数量', dataIndex: 'value', key: 'value' },
  ]
  const tableData = result
    ? [
        { key: 'inserted', label: '新增入库', value: result.inserted },
        { key: 'skipped', label: '重复跳过', value: result.skipped },
        { key: 'errors', label: '错误行数', value: result.errors.length },
      ]
    : []

  if (!userLoaded) {
    return <Card title="配置后台 — 数据上传" loading />
  }

  if (!isAdmin) {
    return (
      <Card title="配置后台">
        <Alert
          type="warning"
          message="权限不足"
          description="CSV 上传仅管理员可操作。"
          showIcon
        />
      </Card>
    )
  }

  return (
    <Card title="配置后台 — 数据上传">
      <Dragger
        accept=".csv"
        multiple={false}
        showUploadList={false}
        customRequest={handleUpload}
        disabled={loading}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽 CSV 文件到此处上传</p>
        <p className="ant-upload-hint">
          支持 GBK / UTF-8 编码，37 列平台使用费特征文件，按服务费订单号自动去重
        </p>
      </Dragger>

      {result && (
        <div style={{ marginTop: 24 }}>
          <Table
            columns={columns}
            dataSource={tableData}
            pagination={false}
            size="small"
          />
          {result.errors.length > 0 && (
            <Alert
              style={{ marginTop: 12 }}
              type="error"
              message="部分行解析失败"
              description={
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {result.errors.map((e, i) => (
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
  )
}
