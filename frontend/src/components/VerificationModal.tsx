import { useState } from 'react'
import { useResendApiVerifyResendPost, useVerifyApiVerifyPost } from '../api/generated/default/default'
import './VerificationModal.css'

type Props = {
  onVerified: (verifiedAt: string | null | undefined) => void
  onClose: () => void
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { data?: { detail?: { error?: string; retry_after_seconds?: number } } } })
      .response
    const detail = response?.data?.detail
    if (detail?.error === 'invalid_code') return 'That code was incorrect. Please try again.'
    if (detail?.error === 'code_expired') return 'That code has expired. Request a new one below.'
    if (detail?.error === 'too_many_attempts') return 'Too many attempts. Request a new code below.'
    if (detail?.error === 'cooldown') {
      const seconds = detail?.retry_after_seconds ?? 0
      return `Please wait ${seconds}s before requesting another code.`
    }
  }
  return fallback
}

export function VerificationModal({ onVerified, onClose }: Props) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [resendMessage, setResendMessage] = useState<string | null>(null)

  const verifyMutation = useVerifyApiVerifyPost()
  const resendMutation = useResendApiVerifyResendPost()

  async function handleSubmit() {
    setError(null)
    setResendMessage(null)
    const trimmed = code.trim()
    if (!/^\d{6}$/.test(trimmed)) {
      setError('Enter the 6-digit code.')
      return
    }
    try {
      const response = await verifyMutation.mutateAsync({ data: { code: trimmed } })
      onVerified(response.verified_at)
    } catch (err) {
      setError(extractErrorMessage(err, 'Verification failed — please try again.'))
    }
  }

  async function handleResend() {
    setError(null)
    setResendMessage(null)
    try {
      await resendMutation.mutateAsync()
      setResendMessage('A new code has been sent.')
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not resend a code right now.'))
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <h2>Enter verification code</h2>
        <p>We texted a 6-digit code to the phone number on file.</p>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="000000"
          inputMode="numeric"
          maxLength={6}
          autoFocus
        />
        {error && <p className="modal-error">{error}</p>}
        {resendMessage && <p className="modal-success">{resendMessage}</p>}
        <div className="modal-actions">
          <button type="button" onClick={handleSubmit} disabled={verifyMutation.isPending}>
            {verifyMutation.isPending ? 'Verifying…' : 'Verify'}
          </button>
          <button type="button" className="modal-secondary" onClick={handleResend} disabled={resendMutation.isPending}>
            Resend code
          </button>
        </div>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
    </div>
  )
}
