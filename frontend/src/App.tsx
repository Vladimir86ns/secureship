import { useState } from 'react'
import { sendChatMessage } from './api'
import './App.css'

type Message = { role: 'user' | 'assistant'; content: string }

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInput('')
    setLoading(true)
    try {
      const reply = await sendChatMessage(text)
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section id="chat">
      <h1>SecureShip Chat</h1>
      <div id="messages">
        {messages.map((m, i) => (
          <p key={i} className={m.role}>
            <strong>{m.role === 'user' ? 'You' : 'Assistant'}:</strong> {m.content}
          </p>
        ))}
        {loading && <p>Thinking…</p>}
      </div>
      {error && <p className="error">{error}</p>}
      <div id="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Type a message…"
        />
        <button type="button" onClick={handleSend} disabled={loading}>
          Send
        </button>
      </div>
    </section>
  )
}

export default App
