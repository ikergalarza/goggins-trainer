interface DeleteButtonProps {
  onDelete: () => void
  label: string
}

// Área táctil de 44×44 (mínimo recomendado en móvil) — el icono va más pequeño
// dentro, pero la zona pulsable es el botón entero.
export default function DeleteButton({ onDelete, label }: DeleteButtonProps) {
  return (
    <button
      type="button"
      onClick={onDelete}
      aria-label={label}
      title={label}
      className="shrink-0 h-11 w-11 flex items-center justify-center rounded-lg bg-gray-800/50 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400 active:bg-red-500/25 active:text-red-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M3 6h18" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        <line x1="10" y1="11" x2="10" y2="17" />
        <line x1="14" y1="11" x2="14" y2="17" />
      </svg>
    </button>
  )
}
