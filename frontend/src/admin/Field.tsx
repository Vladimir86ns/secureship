import type { InputHTMLAttributes } from 'react'

// The same limits as backend/admin_schemas.py (Text, PackageIn.description); the server still checks them.
export const TEXT_MAX_LENGTH = 200
export const DESCRIPTION_MAX_LENGTH = 500

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange'> & {
  label: string
  onChange: (value: string) => void
}

export function Field({ label, onChange, ...input }: FieldProps) {
  return (
    <label>
      {label}
      <input {...input} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
