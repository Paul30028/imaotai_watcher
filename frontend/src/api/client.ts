import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const client = axios.create({ baseURL: '/api' })

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client

/** Pull FastAPI's {"detail": "..."} out of an axios error, falling back to
 * a generic message. Backend errors (duplicate phone, i茅台 rate-limited,
 * etc.) are meaningful and specific -- swallowing them behind a generic
 * "check your input" message is what makes a user retry the wrong thing. */
export function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === 'string' && detail ? detail : fallback
}
