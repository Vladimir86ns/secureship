import { useEffect, useRef, useState } from 'react'
import { useChatApiChatPost, useGetSessionApiSessionGet } from './api/generated/default/default'
import type { ChatTurn } from './api/generated/models'
import { VerificationModal } from './components/VerificationModal'
import type { DisplayMessage } from './types'
import './App.css'

const REVEAL_STAGGER_MS = 500
// Section 6.2b: the chat window changes color when this step of the scripted human hand-off is shown
const COLOR_SHIFT_STEP = 'color_shift'

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
  const [humanMode, setHumanMode] = useState(false)
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
    setHumanMode(data.transcript.some((m) => m.escalation_step === COLOR_SHIFT_STEP))
    setRequiresCodeModal(data.requires_code_modal)
  }, [sessionQuery.data])

  function revealMessages(newMessages: ChatTurn[]) {
    newMessages.forEach((m, i) => {
      setTimeout(
        () => {
          setMessages((prev) => [...prev, { ...m, key: nextKey() }])
          // after "Acknowledging" is shown, together with the "ColorShift" message - not before the sequence
          if (m.escalation_step === COLOR_SHIFT_STEP) setHumanMode(true)
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
      setRequiresCodeModal(response.requires_code_modal)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section id="chat" className={humanMode ? 'chat--human' : undefined}>
      <div id="chat-header">
        <h1>SecureShip Chat</h1>
        {verifiedAt && <span className="verified-badge">✓ Identity verified</span>}
      </div>
      <div id="messages">
        {messages.map((m) =>
          m.role === 'system_event' ? (
            <p key={m.key} className="system-event">
              {m.content}
            </p>
          ) : (
            <div key={m.key} className={`message-row ${m.role}`}>
              <div className={`bubble ${m.role}`}>
                <strong>{m.role === 'user' ? 'You' : 'Assistant'}:</strong> {m.content}
              </div>
            </div>
          ),
        )}
        {loading && (
          <div className="message-row assistant">
            <div className="bubble assistant bubble-loading" aria-live="polite">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}
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
