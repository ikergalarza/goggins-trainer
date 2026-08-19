import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import ChatPanel from './ChatPanel'

// Burbuja flotante 💀 visible en toda la app autenticada. Al pulsarla abre el
// chat con Goggins SOBRE la pantalla actual, sin navegar: en móvil como panel
// a pantalla casi completa que sube desde abajo; en escritorio como panel
// lateral derecho. En /chat no se muestra (ya estás en el chat).
export default function GogginsBubble() {
  const [open, setOpen] = useState(false)
  // El ChatPanel no se monta hasta la primera apertura (evita cargar el
  // historial en cada página); después se mantiene montado aunque se cierre,
  // para no recargar el historial al reabrir.
  const [mounted, setMounted] = useState(false)
  const location = useLocation()
  const onChatPage = location.pathname === '/chat'

  // En /chat todo se oculta (burbuja y panel): la propia página ya es el chat.
  // El estado `open` se conserva, así que al salir de /chat se recupera tal cual.
  const visible = open && !onChatPage

  // Cerrar con Escape mientras el panel está visible.
  useEffect(() => {
    if (!visible) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [visible])

  const handleOpen = () => {
    setMounted(true)
    setOpen(true)
  }

  return (
    <>
      {/* Burbuja: en móvil queda por encima de la barra inferior (+ safe area) */}
      {!onChatPage && !open && (
        <button
          onClick={handleOpen}
          aria-label="Hablar con Goggins"
          className="fixed right-4 z-30 w-14 h-14 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-700 text-2xl shadow-lg shadow-red-950/60 active:scale-95 transition-transform max-md:bottom-[calc(5rem+env(safe-area-inset-bottom))] md:bottom-6"
        >
          💀
        </button>
      )}

      {mounted && (
        <>
          {/* Fondo oscurecido: cierra el panel al tocarlo */}
          <div
            onClick={() => setOpen(false)}
            aria-hidden="true"
            className={`fixed inset-0 z-40 bg-black/60 transition-[opacity,visibility] duration-300 ${
              visible ? 'visible opacity-100' : 'invisible opacity-0'
            }`}
          />

          {/* Panel: móvil = hoja desde abajo casi a pantalla completa; md+ = lateral derecho */}
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Chat con Goggins"
            className={`fixed z-40 flex flex-col bg-gray-950 border-gray-800 shadow-2xl inset-x-0 bottom-0 top-10 rounded-t-2xl border-t md:left-auto md:right-0 md:top-0 md:w-[420px] md:max-w-full md:rounded-none md:border-t-0 md:border-l transition-[transform,visibility] duration-300 ease-out ${
              visible
                ? 'visible translate-y-0 md:translate-x-0'
                : 'invisible translate-y-full md:translate-y-0 md:translate-x-full'
            }`}
          >
            {/* Cabecera del panel */}
            <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-2 border-b border-gray-800">
              <p className="font-black tracking-tight text-white">💀 Goggins</p>
              <button
                onClick={() => setOpen(false)}
                aria-label="Cerrar chat"
                className="min-h-11 min-w-11 flex items-center justify-center rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 active:bg-gray-700 transition-colors"
              >
                <span className="text-xl leading-none">✕</span>
              </button>
            </div>

            {/* Contenido: el mismo ChatPanel que usa la página /chat */}
            <div
              className="flex-1 min-h-0 px-3 pt-3"
              // Safe area inferior del iPhone para que el input no quede pegado al borde.
              style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}
            >
              <ChatPanel variant="panel" />
            </div>
          </div>
        </>
      )}
    </>
  )
}
