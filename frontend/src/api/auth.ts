import client from './client'

export const login = (username: string, password: string) =>
  client.post<{ access_token: string }>('/auth/login', { username, password })

export const getMe = () =>
  client.get<{ id: number; username: string; role: string }>('/auth/me')

export const refresh = () =>
  client.post<{ access_token: string }>('/auth/refresh')
