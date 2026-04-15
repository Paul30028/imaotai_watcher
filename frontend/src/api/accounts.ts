import client from './client'

export interface Account {
  id: number; phone: string; device_id: string; city_code: string
  status: 'active' | 'expired'; last_login: string | null; created_at: string
}

export const listAccounts = () => client.get<Account[]>('/accounts')
export const createAccount = (phone: string, city_code: string) =>
  client.post<Account>('/accounts', { phone, city_code })
export const updateAccount = (id: number, data: { city_code?: string; status?: string }) =>
  client.put<Account>(`/accounts/${id}`, data)
export const deleteAccount = (id: number) => client.delete(`/accounts/${id}`)
export const sendVerifyCode = (id: number) => client.post(`/accounts/${id}/verify`)
export const accountLogin = (id: number, verify_code: string) =>
  client.post<Account>(`/accounts/${id}/login`, { verify_code })
