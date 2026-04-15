import { useState, useEffect } from 'react'
import { Form, Space, DatePicker, Select, Button, Table, Tag, message } from 'antd'
import type { TablePaginationConfig } from 'antd'
import type { Dayjs } from 'dayjs'
import { listLogs, type PurchaseLog } from '../api/logs'
import { listAccounts, type Account } from '../api/accounts'

const { RangePicker } = DatePicker

interface FilterValues {
  dateRange?: [Dayjs, Dayjs]
  account_id?: number
  status?: string
}

const STATUS_COLORS: Record<string, string> = {
  success: 'green',
  fail: 'red',
  retry: 'orange',
}

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  fail: '失败',
  retry: '重试',
}

export default function Logs() {
  const [form] = Form.useForm<FilterValues>()
  const [logs, setLogs] = useState<PurchaseLog[]>([])
  const [total, setTotal] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [filters, setFilters] = useState<Omit<FilterValues, 'dateRange'> & { date_from?: string; date_to?: string }>({})

  const PAGE_SIZE = 20

  const fetchAccounts = async () => {
    try {
      const res = await listAccounts()
      setAccounts(res.data)
    } catch {
      // silently fail for account list
    }
  }

  const fetchLogs = async (page: number, activeFilters: typeof filters) => {
    setLoading(true)
    try {
      const res = await listLogs({
        page,
        page_size: PAGE_SIZE,
        ...activeFilters,
      })
      setLogs(res.data.items)
      setTotal(res.data.total)
    } catch {
      message.error('获取日志失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAccounts()
    fetchLogs(1, {})
  }, [])

  const handleQuery = () => {
    const values = form.getFieldsValue()
    const newFilters: typeof filters = {}

    if (values.account_id !== undefined) {
      newFilters.account_id = values.account_id
    }
    if (values.status) {
      newFilters.status = values.status
    }
    if (values.dateRange && values.dateRange.length === 2) {
      newFilters.date_from = values.dateRange[0].format('YYYY-MM-DD')
      newFilters.date_to = values.dateRange[1].format('YYYY-MM-DD')
    }

    setFilters(newFilters)
    setCurrentPage(1)
    fetchLogs(1, newFilters)
  }

  const handlePageChange = (pagination: TablePaginationConfig) => {
    const page = pagination.current ?? 1
    setCurrentPage(page)
    fetchLogs(page, filters)
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'purchased_at',
      key: 'purchased_at',
      render: (val: string) => new Date(val).toLocaleString('zh-CN'),
    },
    {
      title: '账号ID',
      dataIndex: 'account_id',
      key: 'account_id',
    },
    {
      title: '商品名称',
      dataIndex: 'item_name',
      key: 'item_name',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={STATUS_COLORS[status] ?? 'default'}>
          {STATUS_LABELS[status] ?? status}
        </Tag>
      ),
    },
    {
      title: '返回信息',
      dataIndex: 'message',
      key: 'message',
      render: (msg: string | null) => msg ?? '-',
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Form.Item name="dateRange" label="日期范围">
            <RangePicker />
          </Form.Item>
          <Form.Item name="account_id" label="账号">
            <Select
              allowClear
              placeholder="全部账号"
              style={{ width: 160 }}
              options={accounts.map((a) => ({ label: a.phone, value: a.id }))}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              allowClear
              placeholder="全部"
              style={{ width: 120 }}
              options={[
                { label: '成功', value: 'success' },
                { label: '失败', value: 'fail' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" onClick={handleQuery}>
              查询
            </Button>
          </Form.Item>
        </Space>
      </Form>

      <Table<PurchaseLog>
        rowKey="id"
        loading={loading}
        dataSource={logs}
        columns={columns}
        onChange={handlePageChange}
        pagination={{
          current: currentPage,
          pageSize: PAGE_SIZE,
          total,
          showTotal: (t) => `共 ${t} 条`,
        }}
      />
    </div>
  )
}
