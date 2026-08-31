import client from './client'

export interface Account {
  id: number; phone: string; device_id: string; user_id: string | null
  province_name: string; city_name: string; lat: string; lng: string
  shop_type: number; random_minute: boolean; fixed_minute: number | null; target_minute: number | null
  status: 'active' | 'expired'; last_login: string | null; created_at: string
}

export interface AccountCreatePayload {
  phone: string
  province_name: string
  city_name: string
  lat: string
  lng: string
  shop_type: number
  random_minute: boolean
  fixed_minute?: number | null
}

export interface AccountUpdatePayload {
  province_name?: string
  city_name?: string
  lat?: string
  lng?: string
  shop_type?: number
  random_minute?: boolean
  fixed_minute?: number | null
  status?: string
}

export interface TodayItem {
  item_id: string
  item_code: string | null
  title: string | null
}

export const listAccounts = () => client.get<Account[]>('/accounts')
export const createAccount = (data: AccountCreatePayload) => client.post<Account>('/accounts', data)
export const updateAccount = (id: number, data: AccountUpdatePayload) =>
  client.put<Account>(`/accounts/${id}`, data)
export const deleteAccount = (id: number) => client.delete(`/accounts/${id}`)
export const sendVerifyCode = (id: number) => client.post(`/accounts/${id}/verify`)
export const accountLogin = (id: number, verify_code: string) =>
  client.post<Account>(`/accounts/${id}/login`, { verify_code })
export const getTodayItems = () => client.get<TodayItem[]>('/accounts/today-items')
