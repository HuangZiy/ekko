export function EkkoLogo({ size = 28 }: { size?: number }) {
  const fontSize = size * 0.85

  return (
    <span
      className="font-bold tracking-tight text-[var(--accent)]"
      style={{ fontSize: `${fontSize}px`, lineHeight: 1 }}
    >
      Ekko
    </span>
  )
}
