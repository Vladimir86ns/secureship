const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function sendChatMessage(message: string): Promise<string> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) {
    throw new Error(`Chat request failed (${res.status})`)
  }
  const data = await res.json()
  return data.reply as string
}
