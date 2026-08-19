import ChatPanel from '../components/ChatPanel'

// Página completa del chat (/chat): envoltorio fino sobre ChatPanel, donde vive
// toda la lógica. El mismo panel se reutiliza en la burbuja flotante (GogginsBubble).
export default function Chat() {
  return <ChatPanel variant="page" />
}
