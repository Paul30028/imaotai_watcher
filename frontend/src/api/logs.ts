import client from './client'

export interface PurchaseLog {
  id: number; account_id: number; item_code: string; item_name: string
  status: string; message: string | null; purchased_at: string
}

export interface StatsData {
  total_accounts: number; today_success: number; today_fail: number
  trend: { date: string; success: number; fail: number }[]
}

export const listLogs = (params: {
  page?: number; page_size?: number; account_id?: number; status?: string
  date_from?: string; date_to?: string
}) => client.get<{ total: number; items: PurchaseLog[] }>('/logs', { params })

export const getStats = () => client.get<StatsData>('/logs/stats')
