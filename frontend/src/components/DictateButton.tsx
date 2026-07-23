import { useEffect, useRef, useState } from 'react'

/* La Web Speech API no está en las definiciones de TypeScript, así que
   declaramos aquí lo mínimo que usamos. */
interface SpeechAlternative {
  transcript: string
}
interface SpeechResult {
  isFinal: boolean
  0: SpeechAlternative
}
interface SpeechResultEvent {
  resultIndex: number
  results: { length: number; [i: number]: SpeechResult }
}
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((e: SpeechResultEvent) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}
type RecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

interface DictateButtonProps {
  /** Texto actual del campo; el dictado se añade a continuación. */
  value: string
  onChange: (v: string) => void
  onError?: (msg: string) => void
  disabled?: boolean
}

export default function DictateButton({ value, onChange, onError, disabled }: DictateButtonProps) {
  const [supported] = useState(() => getRecognitionCtor() !== null)
  const [listening, setListening] = useState(false)

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  // Texto que ya había escrito antes de empezar a dictar.
  const baseRef = useRef('')
  // Trozos ya dados por definitivos en esta sesión de dictado.
  const finalRef = useRef('')
  // Distingue "ha parado solo por un silencio" de "el usuario ha pulsado parar".
  const wantListeningRef = useRef(false)
  // onresult se dispara fuera de React; sin esto usaría un `onChange` congelado.
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    return () => {
      wantListeningRef.current = false
      recognitionRef.current?.abort()
    }
  }, [])

  const stop = () => {
    wantListeningRef.current = false
    recognitionRef.current?.stop()
    setListening(false)
  }

  const start = () => {
    const Ctor = getRecognitionCtor()
    if (!Ctor) return

    baseRef.current = value.trim()
    finalRef.current = ''

    const rec = new Ctor()
    rec.lang = 'es-ES'
    rec.continuous = true
    rec.interimResults = true

    rec.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) finalRef.current += res[0].transcript
        else interim += res[0].transcript
      }
      const dictated = (finalRef.current + interim).trim()
      onChangeRef.current([baseRef.current, dictated].filter(Boolean).join(' '))
    }

    rec.onerror = (e) => {
      // Un silencio largo no es un fallo: dejamos que onend lo reanude.
      if (e.error === 'no-speech' || e.error === 'aborted') return
      wantListeningRef.current = false
      setListening(false)
      onError?.(
        e.error === 'not-allowed' || e.error === 'service-not-allowed'
          ? 'No hay permiso para usar el micrófono. Actívalo en los ajustes del navegador.'
          : `No se pudo dictar (${e.error})`,
      )
    }

    rec.onend = () => {
      // Safari en iOS corta el reconocimiento tras cada pausa. Si el usuario no
      // ha pulsado parar, lo reanudamos para que pueda hablar del tirón.
      if (wantListeningRef.current) {
        // Lo ya reconocido pasa a ser la nueva base del siguiente tramo.
        baseRef.current = [baseRef.current, finalRef.current.trim()].filter(Boolean).join(' ')
        finalRef.current = ''
        try {
          rec.start()
          return
        } catch {
          /* si no deja reiniciar, caemos abajo y paramos */
        }
      }
      setListening(false)
    }

    try {
      rec.start()
      recognitionRef.current = rec
      wantListeningRef.current = true
      setListening(true)
    } catch {
      onError?.('No se pudo iniciar el micrófono')
    }
  }

  // En navegadores sin soporte (Firefox) no pintamos nada: el teclado del móvil
  // sigue teniendo su propio botón de dictado.
  if (!supported) return null

  return (
    <button
      type="button"
      onClick={listening ? stop : start}
      disabled={disabled}
      aria-label={listening ? 'Parar de dictar' : 'Dictar mensaje por voz'}
      aria-pressed={listening}
      title={listening ? 'Parar de dictar' : 'Dictar mensaje por voz'}
      className={`shrink-0 h-11 w-11 flex items-center justify-center rounded-xl transition-colors disabled:opacity-40 ${
        listening
          ? 'bg-red-600 text-white animate-pulse'
          : 'bg-gray-900 border border-gray-800 text-gray-400 hover:text-white hover:border-gray-700 active:bg-gray-800'
      }`}
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="22" />
      </svg>
    </button>
  )
}
