import { useState, useEffect } from 'react'
import { Card, Button, Input, TimePicker, message, Modal, Space, Typography } from 'antd'
import dayjs, { Dayjs } from 'dayjs'
import { getSchedulerStatus, updateSchedulerConfig, triggerPurchase } from '../api/scheduler'
import { getNotifySettings, updateNotifySettings, testNotify } from '../api/settings'

const { Title } = Typography

export default function Settings() {
  const [scheduleTime, setScheduleTime] = useState<Dayjs | null>(null)
  const [savingSchedule, setSavingSchedule] = useState(false)

  const [sendKey, setSendKey] = useState('')
  const [savingNotify, setSavingNotify] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)

  const [triggering, setTriggering] = useState(false)

  useEffect(() => {
    getSchedulerStatus()
      .then((res) => {
        const time = res.data.schedule_time
        if (time) {
          setScheduleTime(dayjs(time, 'HH:mm'))
        }
      })
      .catch(() => {
        message.error('获取申购时间配置失败')
      })

    getNotifySettings()
      .then((res) => {
        setSendKey(res.data.send_key ?? '')
      })
      .catch(() => {
        message.error('获取通知配置失败')
      })
  }, [])

  const handleSaveSchedule = async () => {
    if (!scheduleTime) {
      message.error('请选择申购时间')
      return
    }
    setSavingSchedule(true)
    try {
      await updateSchedulerConfig(scheduleTime.format('HH:mm'))
      message.success('申购时间保存成功')
    } catch {
      message.error('申购时间保存失败')
    } finally {
      setSavingSchedule(false)
    }
  }

  const handleSaveNotify = async () => {
    setSavingNotify(true)
    try {
      await updateNotifySettings(sendKey)
      message.success('通知配置保存成功')
    } catch {
      message.error('通知配置保存失败')
    } finally {
      setSavingNotify(false)
    }
  }

  const handleTestNotify = async () => {
    setTestingNotify(true)
    try {
      await testNotify()
      message.success('测试通知已发送')
    } catch {
      message.error('发送测试通知失败')
    } finally {
      setTestingNotify(false)
    }
  }

  const handleTriggerPurchase = () => {
    Modal.confirm({
      title: '确认立即申购',
      content: '确定要立即触发申购吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        setTriggering(true)
        try {
          await triggerPurchase()
          message.success('申购已触发')
        } catch {
          message.error('触发申购失败')
        } finally {
          setTriggering(false)
        }
      },
    })
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', padding: '24px' }}>
      <Title level={2}>设置</Title>

      <Card title="申购时间配置">
        <Space>
          <TimePicker
            format="HH:mm"
            value={scheduleTime}
            onChange={(val) => setScheduleTime(val)}
            placeholder="选择时间"
          />
          <Button type="primary" loading={savingSchedule} onClick={handleSaveSchedule}>
            保存
          </Button>
        </Space>
      </Card>

      <Card title="Server酱通知配置">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input
            placeholder="请输入 SendKey"
            value={sendKey}
            onChange={(e) => setSendKey(e.target.value)}
            style={{ maxWidth: 400 }}
          />
          <Space>
            <Button type="primary" loading={savingNotify} onClick={handleSaveNotify}>
              保存
            </Button>
            <Button loading={testingNotify} onClick={handleTestNotify}>
              发送测试通知
            </Button>
          </Space>
        </Space>
      </Card>

      <Card title="手动触发申购">
        <Button type="primary" danger loading={triggering} onClick={handleTriggerPurchase}>
          立即申购
        </Button>
      </Card>
    </Space>
  )
}
