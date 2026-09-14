import { useEffect, useRef, useState } from 'react'
import { useChatApiChatPost, useGetSessionApiSessionGet } from './api/generated/default/default'
import type { ChatTurn } from './api/generated/models'
import { VerificationModal } from './components/VerificationModal'
import type { DisplayMessage } from './types'
import './App.css'

const REVEAL_STAGGER_MS = 500

let keyCounter = 0
function nextKey(): string {
  keyCounter += 1
  return `msg-${keyCounter}`
}

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verifiedAt, setVerifiedAt] = useState<string | null>(null)
  const [escalatedToHumanAt, setEscalatedToHumanAt] = useState<string | null>(null)
  const [requiresCodeModal, setRequiresCodeModal] = useState(false)
  const hydrated = useRef(false)

  const sessionQuery = useGetSessionApiSessionGet()
  const chatMutation = useChatApiChatPost()

  useEffect(() => {
    if (hydrated.current || !sessionQuery.data) return
    hydrated.current = true
    const data = sessionQuery.data
    setMessages(data.transcript.map((m) => ({ ...m, key: nextKey() })))
    setVerifiedAt(data.verified_at ?? null)
    setEscalatedToHumanAt(data.escalated_to_human_at ?? null)
    setRequiresCodeModal(data.requires_code_modal)
  }, [sessionQuery.data])

  function revealMessages(newMessages: ChatTurn[]) {
    newMessages.forEach((m, i) => {
      setTimeout(
        () => {
          setMessages((prev) => [...prev, { ...m, key: nextKey() }])
        },
        i * REVEAL_STAGGER_MS,
      )
    })
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: text, at: new Date().toISOString(), key: nextKey() }])
    setInput('')
    setLoading(true)
    try {
      const response = await chatMutation.mutateAsync({ data: { message: text } })
      revealMessages(response.messages)
      setVerifiedAt(response.verified_at ?? null)
      setEscalatedToHumanAt(response.escalated_to_human_at ?? null)
      setRequiresCodeModal(response.requires_code_modal)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section id="chat">
      <div id="chat-header">
        <h1>SecureShip Chat</h1>
        {verifiedAt && <span className="verified-badge">✓ Identity verified</span>}
      </div>
      {escalatedToHumanAt && <p className="escalated-banner">You're now chatting with a member of our team.</p>}
      <div id="messages">
        {messages.map((m) => (
          <p key={m.key} className={m.role === 'system_event' ? 'system-event' : m.role}>
            {m.role === 'system_event' ? (
              m.content
            ) : (
              <>
                <strong>{m.role === 'user' ? 'You' : 'Assistant'}:</strong> {m.content}
              </>
            )}
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

      {requiresCodeModal && (
        <VerificationModal
          onVerified={(newVerifiedAt) => {
            setRequiresCodeModal(false)
            setVerifiedAt(newVerifiedAt ?? null)
          }}
          onClose={() => setRequiresCodeModal(false)}
        />
      )}
    </section>
  )
}

export default App
