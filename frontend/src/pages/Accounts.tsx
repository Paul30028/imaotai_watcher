import { useEffect, useState } from 'react'
import {
  Button, Form, Input, InputNumber, message, Modal, Popconfirm,
  Radio, Space, Steps, Switch, Table, Tag, Typography
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import type { Account, AccountCreatePayload, AccountUpdatePayload } from '../api/accounts'
import {
  accountLogin,
  createAccount,
  deleteAccount,
  listAccounts,
  sendVerifyCode,
  updateAccount,
} from '../api/accounts'
import { extractErrorMessage } from '../api/client'

const { Title } = Typography

type ModalMode = 'add' | 'refresh' | 'edit' | null

interface AddFlowState {
  step: 0 | 1
  accountId: number | null
}

interface AccountFormValues {
  phone: string
  province_name: string
  city_name: string
  lat: string
  lng: string
  shop_type: number
  random_minute: boolean
  fixed_minute?: number
}

function LocationFields() {
  return (
    <>
      <Space.Compact block>
        <Form.Item
          name="province_name"
          label="省份"
          rules={[{ required: true, message: '请输入省份' }]}
          style={{ width: '50%' }}
        >
          <Input placeholder="如 广东省" />
        </Form.Item>
        <Form.Item
          name="city_name"
          label="城市"
          rules={[{ required: true, message: '请输入城市' }]}
          style={{ width: '50%' }}
        >
          <Input placeholder="如 深圳市" />
        </Form.Item>
      </Space.Compact>
      <Space.Compact block>
        <Form.Item
          name="lat"
          label="纬度"
          rules={[{ required: true, message: '请输入纬度' }]}
          style={{ width: '50%' }}
        >
          <Input placeholder="如 22.543099" />
        </Form.Item>
        <Form.Item
          name="lng"
          label="经度"
          rules={[{ required: true, message: '请输入经度' }]}
          style={{ width: '50%' }}
        >
          <Input placeholder="如 114.057868" />
        </Form.Item>
      </Space.Compact>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        经纬度可在地图 App 上长按定位点获取，用于按距离选择门店（申购类型为"最近门店"时）。
      </Typography.Text>
      <Form.Item name="shop_type" label="门店选择方式" initialValue={1}>
        <Radio.Group>
          <Radio value={1}>本市出货量最大的门店</Radio>
          <Radio value={2}>距离最近的门店</Radio>
        </Radio.Group>
      </Form.Item>
      <Form.Item name="random_minute" label="随机分钟错峰申购" valuePropName="checked" initialValue={true}>
        <Switch />
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prev, cur) => prev.random_minute !== cur.random_minute}
      >
        {({ getFieldValue }) =>
          !getFieldValue('random_minute') && (
            <Form.Item
              name="fixed_minute"
              label="固定分钟 (1-59)"
              rules={[{ required: true, message: '请输入固定分钟' }]}
            >
              <InputNumber min={1} max={59} style={{ width: '100%' }} />
            </Form.Item>
          )
        }
      </Form.Item>
    </>
  )
}

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(false)
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [addFlowState, setAddFlowState] = useState<AddFlowState>({ step: 0, accountId: null })
  const [editTarget, setEditTarget] = useState<Account | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [addForm] = Form.useForm<AccountFormValues>()
  const [verifyForm] = Form.useForm()
  const [editForm] = Form.useForm<AccountFormValues>()

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
    } catch (err) {
      message.error(extractErrorMessage(err, '发送验证码失败'))
      setModalMode(null)
    } finally {
      setSubmitting(false)
    }
  }

  const openEditModal = (account: Account) => {
    setEditTarget(account)
    editForm.setFieldsValue({
      province_name: account.province_name,
      city_name: account.city_name,
      lat: account.lat,
      lng: account.lng,
      shop_type: account.shop_type,
      random_minute: account.random_minute,
      fixed_minute: account.fixed_minute ?? undefined,
    })
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
    let values: AccountFormValues
    try {
      values = await addForm.validateFields()
    } catch {
      return
    }
    setSubmitting(true)
    const payload: AccountCreatePayload = {
      phone: values.phone,
      province_name: values.province_name,
      city_name: values.city_name,
      lat: values.lat,
      lng: values.lng,
      shop_type: values.shop_type,
      random_minute: values.random_minute,
      fixed_minute: values.random_minute ? null : values.fixed_minute,
    }
    let newId: number
    try {
      const res = await createAccount(payload)
      newId = res.data.id
    } catch (err) {
      message.error(extractErrorMessage(err, '添加账号失败，请检查手机号是否正确'))
      setSubmitting(false)
      return
    }
    try {
      await sendVerifyCode(newId)
      message.success('验证码已发送')
      verifyForm.resetFields()
      setAddFlowState({ step: 1, accountId: newId })
    } catch (err) {
      // 账号已经创建成功了，只是这一步发验证码失败（比如被限流）——
      // 关掉弹窗、刷新列表，用户可以之后用"刷新Token"重试，而不是
      // 让 ta 以为要重新走一遍添加账号（那样只会撞上手机号已存在）。
      message.error(extractErrorMessage(err, '发验证码失败'))
      closeModal()
      fetchAccounts()
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
    } catch (err) {
      message.error(extractErrorMessage(err, '验证码错误或已过期'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleEdit = async () => {
    let values: AccountFormValues
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }
    if (!editTarget) return
    setSubmitting(true)
    try {
      const payload: AccountUpdatePayload = {
        province_name: values.province_name,
        city_name: values.city_name,
        lat: values.lat,
        lng: values.lng,
        shop_type: values.shop_type,
        random_minute: values.random_minute,
        fixed_minute: values.random_minute ? null : values.fixed_minute,
      }
      await updateAccount(editTarget.id, payload)
      message.success('更新成功')
      closeModal()
      fetchAccounts()
    } catch (err) {
      message.error(extractErrorMessage(err, '更新失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id)
      message.success('删除成功')
      fetchAccounts()
    } catch (err) {
      message.error(extractErrorMessage(err, '删除失败'))
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
      title: '省市',
      key: 'location',
      render: (_, record) => `${record.province_name} ${record.city_name}`,
    },
    {
      title: '门店类型',
      dataIndex: 'shop_type',
      key: 'shop_type',
      render: (val: number) => (val === 1 ? '本市出货最大' : '距离最近'),
    },
    {
      title: '今日申购分钟',
      key: 'target_minute',
      render: (_, record) =>
        record.target_minute != null
          ? `窗口内第 ${record.target_minute} 分钟`
          : '未分配（凌晨自动分配）',
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
            <LocationFields />
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
          <LocationFields />
        </Form>
      </Modal>
    </div>
  )
}
