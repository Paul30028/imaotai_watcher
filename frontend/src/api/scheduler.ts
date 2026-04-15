import client from './client'

export interface SchedulerStatus {
  alive: boolean; schedule_time: string; last_run_at: string | null; next_run_at: string | null
}

export const getSchedulerStatus = () => client.get<SchedulerStatus>('/scheduler/status')
export const triggerPurchase = () => client.post('/scheduler/trigger')
export const updateSchedulerConfig = (schedule_time: string) =>
  client.put('/scheduler/config', { schedule_time })
