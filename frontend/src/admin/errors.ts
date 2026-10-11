import { isAxiosError } from 'axios'
import type { AdminErrorResponse, HTTPValidationError } from '../api/generated/models'

// Turns an error from a generated admin hook into a message for the admin.
export function adminErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const status = error.response?.status
    if (status === 400 || status === 401) return 'Your admin session is missing or has expired. Please log in again.'
    if (status === 403) return 'This sign-in is not allowed to use the admin panel.'

    const detail = (error.response?.data as AdminErrorResponse | HTTPValidationError | undefined)?.detail
    if (Array.isArray(detail)) {
      return detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join('; ')
    }
    if (detail && 'error_description' in detail) return detail.error_description
    if (!error.response) return 'The backend could not be reached.'
    return `Request failed (${status}).`
  }
  return error instanceof Error ? error.message : 'Something went wrong.'
}
