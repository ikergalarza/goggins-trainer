import { defineConfig } from 'vitest/config'

// Configuración de Vitest para tests unitarios de lógica pura.
// Los tests actuales (helpers de fecha y formateo de series) no necesitan DOM,
// por eso usamos el entorno 'node'. Si en el futuro se testean componentes React,
// cambiar a environment 'jsdom' (requiere instalar jsdom).
export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
