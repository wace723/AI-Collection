import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Select,
  Space,
  Switch,
  message,
} from 'antd'
import { getAIConfig, updateAIConfig } from '../../api/config'
import type { AIConfig, AIConfigUpdate } from '../../types/api'

/** AI 话术配置面板（talk-002）：主管/管理员可配 apikey/baseurl/model */
export default function AIConfigPanel() {
  const [form] = Form.useForm<AIConfigUpdate>()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [config, setConfig] = useState<AIConfig | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getAIConfig()
      setConfig(data)
      form.setFieldsValue({
        provider: data.provider as AIConfigUpdate['provider'],
        base_url: data.base_url ?? '',
        model: data.model ?? '',
        enabled: data.enabled,
        // api_key 不回填明文，留空=保留旧值
        api_key: '',
      })
    } catch {
      /* client 拦截器已提示 */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const payload: AIConfigUpdate = {
        provider: values.provider,
        base_url: values.base_url || undefined,
        model: values.model || undefined,
        enabled: values.enabled,
      }
      // api_key 空则不传（保留旧值）；非空才更新
      if (values.api_key) {
        payload.api_key = values.api_key
      }
      const data = await updateAIConfig(payload)
      setConfig(data)
      form.setFieldValue('api_key', '')
      message.success('AI 配置已保存')
    } catch {
      /* ignore */
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card
      title="AI 话术配置"
      loading={loading}
      style={{ marginBottom: 24 }}
      extra={
        config && !config.from_db ? (
          <Alert type="info" message="当前来自 .env 默认，保存后写入数据库" banner />
        ) : null
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label="Provider"
          name="provider"
          rules={[{ required: true }]}
          tooltip="mock=离线生成；openai_compatible=调用 OpenAI 兼容接口"
        >
          <Select
            options={[
              { value: 'mock', label: 'mock（离线，测试用）' },
              { value: 'openai_compatible', label: 'openai_compatible（真实 LLM）' },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="API Key"
          name="api_key"
          tooltip="留空保存=保留旧值；填入则覆盖。仅主管/管理员可见配置"
        >
          <Input.Password
            placeholder={
              config?.api_key_masked
                ? `当前 ${config.api_key_masked}（留空保留）`
                : '填入 API Key'
            }
          />
        </Form.Item>
        <Form.Item label="Base URL" name="base_url" tooltip="如 https://tianqu.yzw.cn/v1">
          <Input placeholder="OpenAI 兼容接口地址" />
        </Form.Item>
        <Form.Item label="Model" name="model" tooltip="如 glm-5.2 / deepseek-chat">
          <Input placeholder="模型名" />
        </Form.Item>
        <Form.Item label="启用 AI 话术" name="enabled" valuePropName="checked">
          <Switch checkedChildren="开" unCheckedChildren="关" />
        </Form.Item>
        <Space>
          <Button type="primary" loading={saving} onClick={onSave}>
            保存
          </Button>
          <Button onClick={load}>刷新</Button>
        </Space>
      </Form>
    </Card>
  )
}
