import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  Popconfirm,
  message,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
} from '../../api/users'
import type { Role, UserAccount, UserCreate } from '../../types/api'

const roleOptions: { label: string; value: Role }[] = [
  { label: '催收员', value: 'COLLECTOR' },
  { label: '主管', value: 'SUPERVISOR' },
  { label: '管理员', value: 'ADMIN' },
]

/** 员工管理 Tab：账号列表 + 新增/编辑(角色/停用/重置密码)/删除 */
export default function UsersTab() {
  const [users, setUsers] = useState<UserAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      setUsers(await listUsers())
    } catch {
      /* client 拦截器已提示 */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const onCreate = async () => {
    const values = await form.validateFields()
    setCreating(true)
    try {
      const payload: UserCreate = {
        username: values.username,
        password: values.password,
        display_name: values.display_name,
        role: values.role as Role,
      }
      await createUser(payload)
      message.success('账号已创建')
      setCreateOpen(false)
      form.resetFields()
      await load()
    } catch {
      /* ignore */
    } finally {
      setCreating(false)
    }
  }

  const onToggleActive = async (u: UserAccount) => {
    try {
      await updateUser(u.id, { is_active: !u.is_active })
      message.success(u.is_active ? '已停用' : '已启用')
      await load()
    } catch {
      /* ignore */
    }
  }

  const onResetPassword = async (u: UserAccount) => {
    try {
      await updateUser(u.id, { reset_password: true })
      message.success('密码已重置为 admin123')
    } catch {
      /* ignore */
    }
  }

  const onRoleChange = async (u: UserAccount, role: Role) => {
    try {
      await updateUser(u.id, { role })
      message.success('角色已更新')
      await load()
    } catch {
      /* ignore */
    }
  }

  const onDelete = async (u: UserAccount) => {
    try {
      await deleteUser(u.id)
      message.success('账号已删除')
      await load()
    } catch {
      /* ignore */
    }
  }

  const columns: ColumnsType<UserAccount> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '用户名', dataIndex: 'username', width: 120 },
    { title: '姓名', dataIndex: 'display_name', width: 120 },
    {
      title: '角色',
      dataIndex: 'role',
      width: 160,
      render: (role: Role, u: UserAccount) => (
        <Select
          size="small"
          value={role}
          options={roleOptions}
          onChange={(v: Role) => onRoleChange(u, v)}
          style={{ width: 120 }}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (v: boolean) =>
        v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_: unknown, u: UserAccount) => (
        <Space>
          <Popconfirm
            title={u.is_active ? '停用该账号？' : '启用该账号？'}
            onConfirm={() => onToggleActive(u)}
          >
            <Button size="small">{u.is_active ? '停用' : '启用'}</Button>
          </Popconfirm>
          <Popconfirm
            title="重置密码为 admin123？"
            onConfirm={() => onResetPassword(u)}
          >
            <Button size="small">重置密码</Button>
          </Popconfirm>
          <Popconfirm
            title="删除该账号？"
            description="删除后不可恢复"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDelete(u)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="员工账号管理"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            新增账号
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={users}
        pagination={false}
      />
      <Modal
        title="新增账号"
        open={createOpen}
        confirmLoading={creating}
        onOk={onCreate}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 2, max: 64, message: '2-64 字符' },
            ]}
          >
            <Input placeholder="如 collector4" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '至少 6 位' },
            ]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item
            label="姓名"
            name="display_name"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="如 催收员4" />
          </Form.Item>
          <Form.Item
            label="角色"
            name="role"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select options={roleOptions} placeholder="选择角色" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
