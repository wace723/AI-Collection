import { Card, Form, Input, Button, Typography } from 'antd'

export default function Login() {
  // infra-001 仅表单占位，不调 API（infra-002 接入）
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 360 }}>
        <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
          平台使用费催收系统
        </Typography.Title>
        <Form layout="vertical" onFinish={() => {}}>
          <Form.Item label="用户名" name="username">
            <Input placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item label="密码" name="password">
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              登录
            </Button>
          </Form.Item>
        </Form>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          登录功能在 infra-002 实现
        </Typography.Text>
      </Card>
    </div>
  )
}
