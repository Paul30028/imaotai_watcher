import client from './client'

export const getNotifySettings = () => client.get<{ send_key: string }>('/settings/notify')
export const updateNotifySettings = (send_key: string) =>
  client.put('/settings/notify', { send_key })
export const testNotify = () => client.post('/settings/notify/test')
