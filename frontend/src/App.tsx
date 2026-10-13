import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useChatApiChatPost, useGetSessionApiSessionGet } from './api/generated/default/default'
import type { ChatTurn } from './api/generated/models'
import { VerificationModal } from './components/VerificationModal'
import type { DisplayMessage } from './types'
import './App.css'

const REVEAL_STAGGER_MS = 500
// the same limit as ChatRequest.message on the backend (422 above it)
const MAX_MESSAGE_LENGTH = 2000
const AWAITING_CODE = 'awaiting_code'
// Section 6.2b: the chat window changes color when this step of the scripted human hand-off is shown
const COLOR_SHIFT_STEP = 'color_shift'
// how close (px) to the bottom still counts as "reading the latest message"
const NEAR_BOTTOM_PX = 80

let keyCounter = 0
function nextKey(): string {
  keyCounter += 1
  return `msg-${keyCounter}`
}

function chatErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } } | null)?.response?.status
  if (status === 422) return `Message is too long (max ${MAX_MESSAGE_LENGTH} characters).`
  return 'Something went wrong — please try again.'
}

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verifiedAt, setVerifiedAt] = useState<string | null>(null)
  const [humanMode, setHumanMode] = useState(false)
  const [sessionState, setSessionState] = useState<string | null>(null)
  const [codeModalOpen, setCodeModalOpen] = useState(false)
  const hydrated = useRef(false)
  const sessionStateRef = useRef<string | null>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  // Auto-scroll: stays on while the visitor is at the bottom; scrolling up to read turns it off until they come back.
  const followBottom = useRef(true)
  const lastScrollTop = useRef(0)
  const pendingScroll = useRef<'instant' | 'smooth' | null>(null)

  const sessionQuery = useGetSessionApiSessionGet()
  const chatMutation = useChatApiChatPost()

  useEffect(() => {
    if (hydrated.current || !sessionQuery.data) return
    hydrated.current = true
    const data = sessionQuery.data
    setMessages(data.transcript.map((m) => ({ ...m, key: nextKey() })))
    setVerifiedAt(data.verified_at ?? null)
    setHumanMode(data.transcript.some((m) => m.escalation_step === COLOR_SHIFT_STEP))
    sessionStateRef.current = data.state
    setSessionState(data.state)
    setCodeModalOpen(data.requires_code_modal)
    pendingScroll.current = 'instant'
  }, [sessionQuery.data])

  // After every render that adds a message (or the typing indicator): scroll to the bottom when the visitor just sent
  // a message, the history was just loaded, or they were already following the bottom.
  useLayoutEffect(() => {
    const el = messagesRef.current
    if (!el) return
    const behavior = pendingScroll.current ?? (followBottom.current ? 'smooth' : null)
    pendingScroll.current = null
    if (!behavior) return
    followBottom.current = true
    el.scrollTo({ top: el.scrollHeight, behavior })
  }, [messages, loading])

  // Only scrolling UP away from the bottom stops following; the smooth scroll down to new messages never does.
  function handleMessagesScroll() {
    const el = messagesRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX
    if (nearBottom) followBottom.current = true
    else if (el.scrollTop < lastScrollTop.current) followBottom.current = false
    lastScrollTop.current = el.scrollTop
  }

  // The modal opens by itself only when the conversation ENTERS awaiting_code; while it stays there
  // (the visitor closed the modal and asks about something else) the "Enter code" button reopens it.
  function applySessionState(newState: string, requiresCodeModal: boolean) {
    const entered = requiresCodeModal && sessionStateRef.current !== AWAITING_CODE
    sessionStateRef.current = newState
    setSessionState(newState)
    if (entered) setCodeModalOpen(true)
    if (!requiresCodeModal) setCodeModalOpen(false)
  }

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
    pendingScroll.current = 'smooth'
    setLoading(true)
    try {
      const response = await chatMutation.mutateAsync({ data: { message: text } })
      revealMessages(response.messages)
      setVerifiedAt(response.verified_at ?? null)
      applySessionState(response.state, response.requires_code_modal)
    } catch (err) {
      setError(chatErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section id="chat" className={humanMode ? 'chat--human' : undefined}>
      <div id="chat-header">
        <h1>SecureShip Chat</h1>
        {verifiedAt && <span className="verified-badge">✓ Identity verified</span>}
        {sessionState === AWAITING_CODE && !codeModalOpen && (
          <button type="button" className="enter-code-button" onClick={() => setCodeModalOpen(true)}>
            Enter code
          </button>
        )}
      </div>
      <div id="messages" ref={messagesRef} onScroll={handleMessagesScroll}>
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
          maxLength={MAX_MESSAGE_LENGTH}
        />
        <button type="button" onClick={handleSend} disabled={loading}>
          Send
        </button>
      </div>

      {codeModalOpen && (
        <VerificationModal
          onVerified={(newState, newVerifiedAt) => {
            applySessionState(newState, false)
            setVerifiedAt(newVerifiedAt ?? null)
          }}
          onCancelled={(newState) => {
            applySessionState(newState, false)
            // the backend stored the same notice in the transcript; it shows up on reload too
            revealMessages([{ role: 'system_event', content: 'Verification cancelled.', at: new Date().toISOString() }])
          }}
          onClose={() => setCodeModalOpen(false)}
        />
      )}
    </section>
  )
}

export default App
