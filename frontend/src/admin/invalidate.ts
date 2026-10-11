import type { QueryClient } from '@tanstack/react-query'

// After any admin change: refetch every admin list (counts and names shown on other tabs change too).
// Generated query keys start with the endpoint URL, e.g. ["/admin/customers"].
export function invalidateAdminQueries(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => String(query.queryKey[0]).startsWith('/admin/'),
  })
}
