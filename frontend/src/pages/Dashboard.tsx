import { useEffect, useRef, useState } from 'react'
import { Card, Col, Row, Spin, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Line } from '@ant-design/charts'
import dayjs from 'dayjs'
import { getStats, listLogs } from '../api/logs'
import type { PurchaseLog, StatsData } from '../api/logs'
import { getSchedulerStatus } from '../api/scheduler'
import type { SchedulerStatus } from '../api/scheduler'

interface TrendItem {
  date: string
  type: string
  count: number
}

const statusTagColor: Record<string, string> = {
  success: 'green',
  fail: 'red',
  retry: 'orange',
}

const statusTagText: Record<string, string> = {
  success: '成功',
  fail: '失败',
  retry: '重试',
}

const logColumns: ColumnsType<PurchaseLog> = [
  {
    title: '时间',
    dataIndex: 'purchased_at',
    key: 'purchased_at',
    render: (val: string) => dayjs(val).format('YYYY-MM-DD HH:mm:ss'),
    width: 180,
  },
  {
    title: '账号ID',
    dataIndex: 'account_id',
    key: 'account_id',
    width: 80,
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
    width: 80,
    render: (val: string) => (
      <Tag color={statusTagColor[val] ?? 'default'}>
        {statusTagText[val] ?? val}
      </Tag>
    ),
  },
  {
    title: '返回信息',
    dataIndex: 'message',
    key: 'message',
    render: (val: string | null) => val ?? '-',
  },
]

export default function Dashboard() {
  const [statsLoading, setStatsLoading] = useState(true)
  const [logsLoading, setLogsLoading] = useState(true)
  const [stats, setStats] = useState<StatsData | null>(null)
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null)
  const [logs, setLogs] = useState<PurchaseLog[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStats = async () => {
    try {
      const [statsRes, schedulerRes] = await Promise.all([
        getStats(),
        getSchedulerStatus(),
      ])
      setStats(statsRes.data)
      setScheduler(schedulerRes.data)
    } catch {
      message.error('获取统计数据失败')
    } finally {
      setStatsLoading(false)
    }
  }

  const fetchLogs = async () => {
    try {
      const res = await listLogs({ page: 1, page_size: 20 })
      setLogs(res.data.items)
    } catch {
      message.error('获取购买记录失败')
    } finally {
      setLogsLoading(false)
    }
  }

  const fetchAll = async () => {
    await Promise.all([fetchStats(), fetchLogs()])
  }

  useEffect(() => {
    void fetchAll()
    intervalRef.current = setInterval(() => {
      void fetchAll()
    }, 30000)
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  const trendData: TrendItem[] = stats
    ? stats.trend.flatMap((item) => [
        { date: item.date, type: '成功', count: item.success },
        { date: item.date, type: '失败', count: item.fail },
      ])
    : []

  const lineConfig = {
    data: trendData,
    xField: 'date',
    yField: 'count',
    colorField: 'type',
    smooth: true,
    legend: { position: 'top-right' as const },
    xAxis: { label: { autoRotate: true } },
  }

  return (
    <div style={{ padding: 24 }}>
      <Spin spinning={statsLoading}>
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card>
              <div style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>账号总数</div>
              <div style={{ fontSize: 28, fontWeight: 600 }}>
                {stats?.total_accounts ?? '-'}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <div style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>今日成功</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#52c41a' }}>
                {stats?.today_success ?? '-'}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <div style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>今日失败</div>
              <div style={{ fontSize: 28, fontWeight: 600, color: '#ff4d4f' }}>
                {stats?.today_fail ?? '-'}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <div style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>调度器状态</div>
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 600,
                  color: scheduler?.alive ? '#52c41a' : '#ff4d4f',
                }}
              >
                {scheduler === null ? '-' : scheduler.alive ? '运行中' : '已停止'}
              </div>
            </Card>
          </Col>
        </Row>

        <Card title="近7日申购趋势" style={{ marginBottom: 24 }}>
          {trendData.length > 0 ? (
            <Line {...lineConfig} />
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#aaa' }}>
              暂无趋势数据
            </div>
          )}
        </Card>
      </Spin>

      <Card title="最近申购记录">
        <Spin spinning={logsLoading}>
          <Table<PurchaseLog>
            columns={logColumns}
            dataSource={logs}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ x: 700 }}
          />
        </Spin>
      </Card>
    </div>
  )
}
