import { useEffect, useState } from 'react'
import {
  Button, Form, Input, message, Modal, Popconfirm,
  Space, Steps, Table, Tag, Typography
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import type { Account } from '../api/accounts'
import {
  accountLogin,
  createAccount,
  deleteAccount,
  listAccounts,
  sendVerifyCode,
  updateAccount,
} from '../api/accounts'

const { Title } = Typography

type ModalMode = 'add' | 'refresh' | 'edit' | null

interface AddFlowState {
  step: 0 | 1
  accountId: number | null
}

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(false)
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [addFlowState, setAddFlowState] = useState<AddFlowState>({ step: 0, accountId: null })
  const [editTarget, setEditTarget] = useState<Account | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [addForm] = Form.useForm()
  const [verifyForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const res = await listAccounts()
      setAccounts(res.data)
    } catch {
      message.error('获取账号列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAccounts() }, [])

  const openAddModal = () => {
    addForm.resetFields()
    verifyForm.resetFields()
    setAddFlowState({ step: 0, accountId: null })
    setModalMode('add')
  }

  const openRefreshModal = async (account: Account) => {
    verifyForm.resetFields()
    setAddFlowState({ step: 1, accountId: account.id })
    setModalMode('refresh')
    setSubmitting(true)
    try {
      await sendVerifyCode(account.id)
      message.success('验证码已发送')
    } catch {
      message.error('发送验证码失败')
      setModalMode(null)
    } finally {
      setSubmitting(false)
    }
  }

  const openEditModal = (account: Account) => {
    setEditTarget(account)
    editForm.setFieldsValue({ city_code: account.city_code })
    setModalMode('edit')
  }

  const closeModal = () => {
    setModalMode(null)
    setEditTarget(null)
    addForm.resetFields()
    verifyForm.resetFields()
    editForm.resetFields()
  }

  // Step 1: create account + send SMS
  const handleSendCode = async () => {
    let values: { phone: string; city_code: string }
    try {
      values = await addForm.validateFields()
    } catch {
      return
    }
    setSubmitting(true)
    try {
      const res = await createAccount(values.phone, values.city_code)
      const newId = res.data.id
      await sendVerifyCode(newId)
      message.success('验证码已发送')
      verifyForm.resetFields()
      setAddFlowState({ step: 1, accountId: newId })
    } catch {
      message.error('发送验证码失败，请检查手机号是否正确')
    } finally {
      setSubmitting(false)
    }
  }

  // Step 2: verify login
  const handleVerifyLogin = async () => {
    let values: { verify_code: string }
    try {
      values = await verifyForm.validateFields()
    } catch {
      return
    }
    if (!addFlowState.accountId) return
    setSubmitting(true)
    try {
      await accountLogin(addFlowState.accountId, values.verify_code)
      message.success('登录成功')
      closeModal()
      fetchAccounts()
    } catch {
      message.error('验证码错误或已过期')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEdit = async () => {
    let values: { city_code: string }
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }
    if (!editTarget) return
    setSubmitting(true)
    try {
      await updateAccount(editTarget.id, { city_code: values.city_code })
      message.success('更新成功')
      closeModal()
      fetchAccounts()
    } catch {
      message.error('更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id)
      message.success('删除成功')
      fetchAccounts()
    } catch {
      message.error('删除失败')
    }
  }

  const formatDate = (val: string | null) =>
    val ? dayjs(val).format('YYYY-MM-DD HH:mm') : '-'

  const columns: ColumnsType<Account> = [
    {
      title: '手机号',
      dataIndex: 'phone',
      key: 'phone',
    },
    {
      title: '城市编码',
      dataIndex: 'city_code',
      key: 'city_code',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: 'active' | 'expired') =>
        status === 'active'
          ? <Tag color="green">正常</Tag>
          : <Tag color="red">token过期</Tag>,
    },
    {
      title: '最近登录',
      dataIndex: 'last_login',
      key: 'last_login',
      render: (val: string | null) => formatDate(val),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openRefreshModal(record)}>
            刷新Token
          </Button>
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该账号？"
            onConfirm={() => handleDelete(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const isAddOrRefresh = modalMode === 'add' || modalMode === 'refresh'

  const addModalFooter = addFlowState.step === 0
    ? [
        <Button key="cancel" onClick={closeModal}>取消</Button>,
        <Button key="send" type="primary" loading={submitting} onClick={handleSendCode}>
          发送验证码
        </Button>,
      ]
    : [
        <Button key="cancel" onClick={closeModal}>取消</Button>,
        <Button key="login" type="primary" loading={submitting} onClick={handleVerifyLogin}>
          登录
        </Button>,
      ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>账号管理</Title>
        <Button type="primary" onClick={openAddModal}>
          添加账号
        </Button>
      </div>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={accounts}
        columns={columns}
        pagination={{ pageSize: 20 }}
      />

      {/* Add / Refresh Token Modal */}
      <Modal
        title={modalMode === 'refresh' ? '刷新Token' : '添加账号'}
        open={isAddOrRefresh}
        onCancel={closeModal}
        footer={addModalFooter}
        destroyOnClose
      >
        <Steps
          current={addFlowState.step}
          items={[{ title: '填写信息' }, { title: '验证登录' }]}
          style={{ marginBottom: 24 }}
        />

        {addFlowState.step === 0 && (
          <Form form={addForm} layout="vertical">
            <Form.Item
              name="phone"
              label="手机号"
              rules={[{ required: true, message: '请输入手机号' }]}
            >
              <Input placeholder="请输入手机号" maxLength={11} />
            </Form.Item>
            <Form.Item
              name="city_code"
              label="城市编码"
              rules={[{ required: true, message: '请输入城市编码' }]}
            >
              <Input placeholder="请输入城市编码，如 510100" />
            </Form.Item>
          </Form>
        )}

        {addFlowState.step === 1 && (
          <Form form={verifyForm} layout="vertical">
            <Form.Item
              name="verify_code"
              label="验证码"
              rules={[{ required: true, message: '请输入验证码' }]}
            >
              <Input placeholder="请输入短信验证码" maxLength={6} />
            </Form.Item>
          </Form>
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal
        title="编辑账号"
        open={modalMode === 'edit'}
        onCancel={closeModal}
        onOk={handleEdit}
        okText="保存"
        cancelText="取消"
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="city_code"
            label="城市编码"
            rules={[{ required: true, message: '请输入城市编码' }]}
          >
            <Input placeholder="请输入城市编码，如 510100" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
