import axios, { type AxiosRequestConfig } from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

export const apiMutator = <T>(config: AxiosRequestConfig): Promise<T> =>
  axiosInstance.request<T>(config).then((res) => res.data)

export default apiMutator
