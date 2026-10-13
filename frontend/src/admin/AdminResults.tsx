import { useLayoutEffect, useRef, type ReactNode } from 'react'

// The list area under the toolbar. While a search is active it never gets shorter than it was before the search,
// so fewer rows (or "No matches for …") do not pull the page up or move the scroll position. Display only.
export function AdminResults({ query, children }: { query: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const lastHeight = useRef(0)
  const lockedHeight = useRef<number | null>(null)

  // Runs before paint: the height from the previous render becomes the floor, so the shrink is never visible.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (query) {
      lockedHeight.current = Math.max(lockedHeight.current ?? 0, lastHeight.current)
      el.style.minHeight = `${lockedHeight.current}px`
    } else {
      lockedHeight.current = null
      el.style.minHeight = ''
    }
    lastHeight.current = el.offsetHeight
  })

  return (
    <div ref={ref} className="admin-results">
      {children}
    </div>
  )
}
