type Props = {
  value: string
  onChange: (value: string) => void
  placeholder: string
}

export function SearchBox({ value, onChange, placeholder }: Props) {
  return (
    <input
      type="search"
      className="admin-search"
      aria-label={placeholder}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
