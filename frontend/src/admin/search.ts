// Admin list search: filters the list already loaded in the browser (no API call). Case-insensitive, trimmed.

export function normalizeQuery(query: string): string {
  return query.trim().toLowerCase()
}

// Tracking numbers match with or without the spaces and dashes the admin typed ("SS-1234 56" finds "SS123456").
function compact(value: string): string {
  return value.toLowerCase().replace(/[\s-]+/g, '')
}

export function matchesText(query: string, values: (string | null | undefined)[]): boolean {
  return values.some((v) => v != null && v.toLowerCase().includes(query))
}

export function matchesTracking(query: string, trackingNumber: string | null | undefined): boolean {
  const q = compact(query)
  return q !== '' && trackingNumber != null && compact(trackingNumber).includes(q)
}
