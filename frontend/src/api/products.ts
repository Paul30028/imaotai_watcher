import client from './client'

export interface Product {
  id: number; account_id: number | null; item_code: string; item_name: string; enabled: boolean
}

export const listProducts = (account_id?: number) =>
  client.get<Product[]>('/products', { params: account_id != null ? { account_id } : {} })
export const createProduct = (data: { account_id?: number; item_code: string; item_name: string }) =>
  client.post<Product>('/products', data)
export const updateProduct = (id: number, data: { enabled?: boolean; item_name?: string }) =>
  client.put<Product>(`/products/${id}`, data)
export const deleteProduct = (id: number) => client.delete(`/products/${id}`)
