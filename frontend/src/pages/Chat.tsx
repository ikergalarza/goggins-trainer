import { useEffect, useRef, useState, type ReactNode } from 'react'
import api, { API_BASE, authHeaders } from '../api'
import { useAuth } from '../auth/AuthContext'

// Markdown inline minimalista: **bold**, *italic*, `code`. No depende de libs.
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) {
      nodes.push(<strong key={key++} className="font-bold text-white">{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('`')) {
      nodes.push(<code key={key++} className="bg-black/40 text-red-300 px-1 rounded text-[12px]">{tok.slice(1, -1)}</code>)
    } else {
      nodes.push(<em key={key++} className="italic">{tok.slice(1, -1)}</em>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let listBuf: string[] = []
  const flushList = () => {
    if (listBuf.length === 0) return
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="list-disc list-inside space-y-0.5 my-1">
        {listBuf.map((li, i) => <li key={i}>{renderInline(li)}</li>)}
      </ul>
    )
    listBuf = []
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    const liMatch = line.match(/^\s*[-*]\s+(.*)$/)
    if (liMatch) {
      listBuf.push(liMatch[1])
      continue
    }
    flushList()
    if (line === '') {
      blocks.push(<div key={`sp-${blocks.length}`} className="h-2" />)
    } else {
      blocks.push(<p key={`p-${blocks.length}`}>{renderInline(line)}</p>)
    }
  }
  flushList()
  return <div className="space-y-0">{blocks}</div>
}

interface ToolEvent {
  name: string
  ok?: boolean
  summary?: string
  input?: any
  state: 'running' | 'done' | 'error'
}

interface Message {
  id?: number
  role: 'user' | 'assistant'
  content: string
  created_at?: string
  toolEvents?: ToolEvent[]
}

const TOOL_LABELS: Record<string, string> = {
  list_workouts: 'Consultando tu plan',
  move_workout: 'Moviendo entreno',
  update_workout: 'Actualizando entreno',
  delete_workout: 'Eliminando entreno',
  add_workout: 'Añadiendo entreno',
  mark_workout_status: 'Marcando entreno',
  shift_plan: 'Desplazando el plan',
  adjust_week_load: 'Ajustando la carga de la semana',
  get_strava_summary: 'Consultando resumen de Strava',
  compare_planned_vs_actual: 'Comparando plan vs. realizado',
}

const SUGGESTIONS = [
  '¿Qué entreno toca hoy?',
  'Mueve la tirada larga del sábado al domingo',
  'Marca el entreno de hoy como completado',
  'Añade series el miércoles, 6x800m',
  'Cambia el de mañana a recovery 30\'',
  'Quita el descanso del viernes',
  '¿Cómo voy con mi preparación?',
  'No tengo ganas de entrenar hoy',
]

export default function Chat() {
  const { effectiveUserId } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamTools, setStreamTools] = useState<ToolEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Cargar historial al montar (y al cambiar de usuario)
  useEffect(() => {
    if (effectiveUserId == null) return
    api.get(`/api/chat/${effectiveUserId}`)
      .then(r => setMessages(r.data))
      .catch(() => {})
  }, [effectiveUserId])

  // Auto-scroll al fondo
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamText])

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim()
    if (!message || streaming || effectiveUserId == null) return

    setError(null)
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: message }])
    setStreaming(true)
    setStreamText('')
    setStreamTools([])

    const url = `${API_BASE}/api/chat/${effectiveUserId}/send_stream`

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ message }),
      })
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let tools: ToolEvent[] = []
      let hadMutation = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const ev of events) {
          const line = ev.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          let payload: any
          try {
            payload = JSON.parse(line.slice(6))
          } catch {
            continue
          }

          if (payload.phase === 'chunk') {
            accumulated += payload.text || ''
            setStreamText(accumulated)
          } else if (payload.phase === 'tool_use') {
            tools = [...tools, { name: payload.name, input: payload.input, state: 'running' }]
            setStreamTools(tools)
          } else if (payload.phase === 'tool_result') {
            // Mark the last running tool with this name as done/error
            const idx = [...tools].reverse().findIndex(t => t.name === payload.name && t.state === 'running')
            if (idx >= 0) {
              const realIdx = tools.length - 1 - idx
              tools = tools.map((t, i) => i === realIdx
                ? { ...t, state: payload.ok ? 'done' : 'error', ok: payload.ok, summary: payload.summary }
                : t)
              setStreamTools(tools)
            }
          } else if (payload.phase === 'mutation') {
            hadMutation = true
          } else if (payload.phase === 'done') {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: payload.content || accumulated,
              toolEvents: tools.length > 0 ? tools : undefined,
            }])
            setStreamText('')
            setStreamTools([])
            if (hadMutation) {
              window.dispatchEvent(new CustomEvent('plan-mutated'))
            }
          } else if (payload.phase === 'error') {
            throw new Error(payload.detail || 'Error desconocido')
          }
        }
      }
    } catch (e: any) {
      setError(e?.message || String(e))
      setStreamText('')
      setStreamTools([])
    } finally {
      setStreaming(false)
    }
  }

  const handleClear = async () => {
    if (effectiveUserId == null) return
    if (!confirm('¿Borrar todo el historial del chat?')) return
    try {
      await api.delete(`/api/chat/${effectiveUserId}`)
      setMessages([])
      setStreamText('')
      setError(null)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-4 h-[calc(100vh-150px)] sm:h-[calc(100vh-180px)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight">💀 Goggins</h1>
          <p className="text-gray-500 text-sm mt-1">Stay hard. No excuses. Habla con tu coach.</p>
        </div>
        <button
          onClick={handleClear}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg text-xs font-bold shrink-0"
        >
          🗑 <span className="hidden sm:inline">Borrar historial</span>
        </button>
      </div>

      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-gray-900 border border-gray-800 rounded-xl p-3 sm:p-4 space-y-4"
      >
        {messages.length === 0 && !streaming && (
          <div className="text-center text-gray-500 mt-8 space-y-4">
            <p className="text-6xl">💀</p>
            <p className="text-sm">Aún no has hablado con Goggins.</p>
            <p className="text-xs text-gray-600">Pídele que <span className="text-red-400 font-bold">modifique tu plan</span>: mover, añadir, quitar o marcar entrenos. También responde sobre técnica, estado y motivación.</p>
            <div className="flex flex-wrap gap-2 justify-center mt-6">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => handleSend(s)}
                  className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs px-3 py-2 rounded-full border border-gray-700"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={m.id ?? i}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[90%] sm:max-w-[85%] rounded-2xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-sm leading-relaxed ${
                m.role === 'user'
                  ? 'bg-red-600 text-white rounded-br-sm whitespace-pre-wrap'
                  : 'bg-gray-800 text-gray-100 border border-gray-700 rounded-bl-sm'
              }`}
            >
              {m.role === 'assistant' && (
                <p className="text-[10px] font-black text-red-400 uppercase tracking-wider mb-1">💀 Goggins</p>
              )}
              {m.toolEvents && m.toolEvents.length > 0 && (
                <ToolEventList events={m.toolEvents} />
              )}
              {m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
            </div>
          </div>
        ))}

        {/* Mensaje en streaming */}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[90%] sm:max-w-[85%] rounded-2xl rounded-bl-sm px-3.5 sm:px-4 py-2.5 sm:py-3 text-sm leading-relaxed bg-gray-800 text-gray-100 border border-red-900/40">
              <p className="text-[10px] font-black text-red-400 uppercase tracking-wider mb-1">💀 Goggins</p>
              {streamTools.length > 0 && <ToolEventList events={streamTools} />}
              {streamText ? <Markdown text={streamText} /> : (streamTools.length === 0 && (
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </span>
              ))}
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-red-400">Error: {error}</p>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={e => {
          e.preventDefault()
          handleSend()
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Escribe a Goggins..."
          disabled={streaming}
          enterKeyHint="send"
          className="flex-1 min-w-0 bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-base sm:text-sm placeholder:text-gray-600 focus:outline-none focus:border-red-700 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white px-4 sm:px-6 py-3 rounded-xl text-sm font-bold transition-colors shrink-0"
        >
          {streaming ? '⏳' : 'Enviar'}
        </button>
      </form>
    </div>
  )
}

function ToolEventList({ events }: { events: ToolEvent[] }) {
  return (
    <div className="mb-2 space-y-1">
      {events.map((t, i) => {
        const label = TOOL_LABELS[t.name] || t.name
        const icon = t.state === 'running' ? '⚙️' : t.state === 'error' ? '⚠️' : '✓'
        const color =
          t.state === 'running'
            ? 'text-gray-400 border-gray-700 bg-gray-900/60'
            : t.state === 'error'
              ? 'text-red-300 border-red-900/60 bg-red-950/40'
              : 'text-green-300 border-green-900/60 bg-green-950/30'
        return (
          <div
            key={i}
            className={`inline-flex items-center gap-2 text-[11px] px-2 py-1 rounded-md border ${color} mr-1`}
          >
            <span className={t.state === 'running' ? 'animate-pulse' : ''}>{icon}</span>
            <span className="font-semibold">{label}</span>
            {t.state !== 'running' && t.summary && (
              <span className="text-gray-400 font-normal truncate max-w-[240px]">— {t.summary}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
