import { useEffect, useRef, useState } from 'react'
import api from '../api'

const USER_ID = 1

interface Message {
  id?: number
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

const SUGGESTIONS = [
  '¿Cómo voy con mi preparación?',
  '¿Qué entreno toca hoy?',
  'No tengo ganas de entrenar hoy',
  '¿Cómo mejoro mi ritmo de umbral?',
  '¿Qué hago si me duele la rodilla?',
]

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Cargar historial al montar
  useEffect(() => {
    api.get(`/api/chat/${USER_ID}`)
      .then(r => setMessages(r.data))
      .catch(() => {})
  }, [])

  // Auto-scroll al fondo
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamText])

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim()
    if (!message || streaming) return

    setError(null)
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: message }])
    setStreaming(true)
    setStreamText('')

    const baseUrl = (import.meta.env.VITE_API_URL as string | undefined) || ''
    const url = `${baseUrl}/api/chat/${USER_ID}/send_stream`

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''

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
          } else if (payload.phase === 'done') {
            setMessages(prev => [...prev, { role: 'assistant', content: payload.content || accumulated }])
            setStreamText('')
          } else if (payload.phase === 'error') {
            throw new Error(payload.detail || 'Error desconocido')
          }
        }
      }
    } catch (e: any) {
      setError(e?.message || String(e))
      setStreamText('')
    } finally {
      setStreaming(false)
    }
  }

  const handleClear = async () => {
    if (!confirm('¿Borrar todo el historial del chat?')) return
    try {
      await api.delete(`/api/chat/${USER_ID}`)
      setMessages([])
      setStreamText('')
      setError(null)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-4 h-[calc(100vh-180px)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black tracking-tight">💀 Goggins</h1>
          <p className="text-gray-500 text-sm mt-1">Stay hard. No excuses. Habla con tu coach.</p>
        </div>
        <button
          onClick={handleClear}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg text-xs font-bold"
        >
          🗑 Borrar historial
        </button>
      </div>

      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4"
      >
        {messages.length === 0 && !streaming && (
          <div className="text-center text-gray-500 mt-8 space-y-4">
            <p className="text-6xl">💀</p>
            <p className="text-sm">Aún no has hablado con Goggins.</p>
            <p className="text-xs text-gray-600">Pregúntale lo que quieras: estado, motivación, técnica, planificación...</p>
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
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-red-600 text-white rounded-br-sm'
                  : 'bg-gray-800 text-gray-100 border border-gray-700 rounded-bl-sm'
              }`}
            >
              {m.role === 'assistant' && (
                <p className="text-[10px] font-black text-red-400 uppercase tracking-wider mb-1">💀 Goggins</p>
              )}
              {m.content}
            </div>
          </div>
        ))}

        {/* Mensaje en streaming */}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm whitespace-pre-wrap bg-gray-800 text-gray-100 border border-red-900/40">
              <p className="text-[10px] font-black text-red-400 uppercase tracking-wider mb-1">💀 Goggins</p>
              {streamText || (
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 bg-red-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </span>
              )}
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
          className="flex-1 bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm placeholder:text-gray-600 focus:outline-none focus:border-red-700 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white px-6 py-3 rounded-xl text-sm font-bold transition-colors"
        >
          {streaming ? '⏳' : 'Enviar'}
        </button>
      </form>
    </div>
  )
}
