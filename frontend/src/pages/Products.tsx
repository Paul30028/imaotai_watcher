import { useEffect, useState } from 'react'
import { Button, Form, Input, message, Modal, Popconfirm, Switch, Table, Tabs } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { listAccounts } from '../api/accounts'
import type { Account } from '../api/accounts'
import { createProduct, deleteProduct, listProducts, updateProduct } from '../api/products'
import type { Product } from '../api/products'

type TabKey = 'global' | string

function ProductTable({
  products,
  loading,
  onToggle,
  onDelete,
}: {
  products: Product[]
  loading: boolean
  onToggle: (id: number, enabled: boolean) => Promise<void>
  onDelete: (id: number) => Promise<void>
}) {
  const columns: ColumnsType<Product> = [
    {
      title: '商品名称',
      dataIndex: 'item_name',
      key: 'item_name',
    },
    {
      title: '商品编码',
      dataIndex: 'item_code',
      key: 'item_code',
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean, record: Product) => (
        <Switch
          checked={enabled}
          onChange={(checked) => onToggle(record.id, checked)}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Product) => (
        <Popconfirm
          title="确认删除该商品？"
          onConfirm={() => onDelete(record.id)}
          okText="确认"
          cancelText="取消"
        >
          <Button type="link" danger>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Table
      rowKey="id"
      columns={columns}
      dataSource={products}
      loading={loading}
      pagination={false}
    />
  )
}

interface AddProductModalProps {
  open: boolean
  accountId: number | null
  onClose: () => void
  onSuccess: () => void
}

function AddProductModal({ open, accountId, onClose, onSuccess }: AddProductModalProps) {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createProduct({
        item_name: values.item_name,
        item_code: values.item_code,
        ...(accountId != null ? { account_id: accountId } : {}),
      })
      message.success('添加商品成功')
      form.resetFields()
      onSuccess()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return
      }
      message.error('添加商品失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = () => {
    form.resetFields()
    onClose()
  }

  return (
    <Modal
      title="添加商品"
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={submitting}
      okText="确认"
      cancelText="取消"
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label="商品名称"
          name="item_name"
          rules={[{ required: true, message: '请输入商品名称' }]}
        >
          <Input placeholder="请输入商品名称" />
        </Form.Item>
        <Form.Item
          label="商品编码"
          name="item_code"
          rules={[{ required: true, message: '请输入商品编码' }]}
        >
          <Input placeholder="请输入商品编码" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default function Products() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [activeTab, setActiveTab] = useState<TabKey>('global')
  const [products, setProducts] = useState<Product[]>([])
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    listAccounts()
      .then((res) => setAccounts(res.data))
      .catch(() => message.error('获取账号列表失败'))
  }, [])

  const fetchProducts = async (tab: TabKey) => {
    setLoadingProducts(true)
    try {
      if (tab === 'global') {
        const res = await listProducts()
        setProducts(res.data)
      } else {
        const accountId = parseInt(tab, 10)
        const res = await listProducts(accountId)
        setProducts(res.data)
      }
    } catch {
      message.error('获取商品列表失败')
    } finally {
      setLoadingProducts(false)
    }
  }

  useEffect(() => {
    fetchProducts(activeTab)
  }, [activeTab])

  const handleTabChange = (key: string) => {
    setActiveTab(key as TabKey)
  }

  const handleToggle = async (id: number, enabled: boolean) => {
    try {
      await updateProduct(id, { enabled })
      setProducts((prev) =>
        prev.map((p) => (p.id === id ? { ...p, enabled } : p))
      )
      message.success('更新成功')
    } catch {
      message.error('更新失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteProduct(id)
      setProducts((prev) => prev.filter((p) => p.id !== id))
      message.success('删除成功')
    } catch {
      message.error('删除失败')
    }
  }

  const currentAccountId: number | null =
    activeTab === 'global' ? null : parseInt(activeTab, 10)

  const tabItems = [
    {
      key: 'global',
      label: '全局默认',
    },
    ...accounts.map((account) => ({
      key: String(account.id),
      label: account.phone,
    })),
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>商品管理</h2>
        <Button type="primary" onClick={() => setModalOpen(true)}>
          添加商品
        </Button>
      </div>

      <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} />

      <ProductTable
        products={products}
        loading={loadingProducts}
        onToggle={handleToggle}
        onDelete={handleDelete}
      />

      <AddProductModal
        open={modalOpen}
        accountId={currentAccountId}
        onClose={() => setModalOpen(false)}
        onSuccess={() => {
          setModalOpen(false)
          fetchProducts(activeTab)
        }}
      />
    </div>
  )
}
