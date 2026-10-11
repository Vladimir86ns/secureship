import type { InputHTMLAttributes } from 'react'

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
