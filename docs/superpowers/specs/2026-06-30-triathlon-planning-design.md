# Mejora del sistema de planificación de entrenamientos (+ Triatlón)

**Fecha:** 2026-06-30
**Rama:** `feature/triathlon-planning` (baseline WIP en `wip/pre-triathlon-baseline`)
**Objetivo global:** que la planificación de entrenamientos esté mucho mejor hecha, con soporte de triatlón, un Goggins capaz de adaptar el plan en directo y mejoras de UX/UI y móvil.

## Contexto del código (estado actual)

- **Backend:** FastAPI + SQLAlchemy 2.0 + PostgreSQL + Alembic. Anthropic SDK. Modelo `claude-opus-4-6` (`backend/app/services/ai_client.py`).
- **Frontend:** React 19 + Vite + Tailwind 4. Sin librería de estado global. Sin tests.
- **Objetivos:** `Goal` (`backend/app/models/goal.py`) con `GoalType` (race, hyrox, weekly_km, fitness, custom) y `sport` (running, hyrox). Form en `frontend/src/pages/Goals.tsx`.
- **Plan:** `Workout` (`backend/app/models/workout.py`) con `WorkoutType` solo de carrera/hyrox/fuerza. Generación vía Claude streaming en `backend/app/services/plan_generator.py`. El cálculo de semanas en backend es Monday-based y correcto (`date.weekday()`).
- **Goggins:** `backend/app/services/goggins_agent.py` + `agent_tools.py`. **Ya tiene 6 tools** (list/move/update/delete/add/mark workout) y contexto de Strava (14 días) + próximos entrenos. Limitado: max_tokens 600, poca proactividad.
- **Strava:** integración completa (`services/strava.py`, `routes/strava.py`), actividades guardadas (Run/Ride/Swim), stats semanales por lunes, detalle con laps/segments.
- **Bug calendario:** `startOfWeek` en `Plan.tsx` calcula bien el lunes; el desfase probable es parseo de fechas en UTC (`new Date("YYYY-MM-DD")`) que salta un día según zona horaria. A diagnosticar con test.

## Decisiones de diseño (aprobadas)

1. **Triatlón:** soportar las 4 distancias estándar (Sprint 0.75/20/5, Olímpico 1.5/40/10, Half/70.3 1.9/90/21.1, Ironman 3.8/180/42.2 km nat/bici/carrera).
2. **Nivel multideporte:** se **infiere de Strava** (volúmenes recientes de Run/Ride/Swim), no se piden datos nuevos al usuario.
3. **Ejecución:** un único workflow con departamentos en paralelo (por fases para no chocar en los mismos archivos), entrega al final.
4. **Modelo:** subir de `claude-opus-4-6` a `claude-opus-4-8`.

## Departamentos (agentes)

### 1. Objetivos / Triatlón (Cimientos)
- `sport`: añadir `triathlon`. `Goal`: nuevo campo `triathlon_distance` (sprint|olympic|half|ironman) y splits objetivo opcionales.
- Módulo `services/triathlon.py` con la config de distancias (nat/bici/carrera por distancia).
- Migración Alembic para columnas nuevas.
- `Goals.tsx`: selector de distancia cuando `sport = triathlon`.

### 2. Generación de Plan (Cimientos + Lógica)
- `WorkoutType`: añadir `swim`, `bike`, `brick`, `transition`, `swim_technique`, `open_water`.
- `plan_generator.py`: prompt + JSON schema multideporte; periodización para la distancia elegida; inyectar volúmenes recientes de Strava por disciplina para inferir nivel.
- **Arreglo del bug de calendario** con test que lo reproduzca (parseo de fechas consistente, semana = lunes).

### 3. Goggins inteligente (Lógica)
- Subir max_tokens (~2500). System prompt más proactivo (analiza carga real vs plan, sugiere subir/bajar).
- Nuevas tools: `shift_plan` (mover plan N días/semanas), `adjust_week_load` (escalar carga %), `get_strava_summary` / `compare_planned_vs_actual` (leer lo realmente hecho).
- Contexto de **ediciones manuales**: `Workout.updated_at` + `modified_by` (ai|user) para que Goggins sepa qué cambió el usuario.

### 4. UX/UI (Presentación)
- Series clarísimas (ej. "6×400m @ Z4, rec 90s"), color por disciplina (nat azul, bici verde, carrera naranja, brick, fuerza), tarjetas legibles. Dueño de `Plan.tsx` y componentes de workout.

### 5. Móvil (Presentación)
- Responsive real: calendario `grid-cols-7` → vista lista/día en móvil, menú hamburguesa (`Layout.tsx`), chat y gráficas adaptadas. Dueño de nav + páginas distintas de `Plan.tsx`.

### 6. Tests (Transversal)
- Montar pytest (backend) + vitest (frontend). Tests de: lógica de semana/fechas (el bug), parseo de plan, config de distancias tri, tools del agente, matching de Strava, CRUD de objetivos con triatlón.

## Orquestación (fases del workflow)

1. **Cimientos** (1 agente): modelos (Goal, Workout enums + updated_at/modified_by), `triathlon.py`, migración, bump de modelo.
2. **Lógica** (paralelo, archivos disjuntos): (a) `plan_generator.py`+`routes/plans.py`; (b) `goggins_agent.py`+`agent_tools.py`+`routes/chat.py`; (c) frontend lógico: fix calendario en `Plan.tsx`, form triatlón en `Goals.tsx`, render de tools nuevas en `Chat.tsx`.
3. **Presentación** (paralelo, dueños disjuntos): UX dueño de `Plan.tsx`/componentes; Móvil dueño de `Layout.tsx`/nav + otras páginas.
4. **Tests + Verificación** (paralelo + verificación): escribir suites; ejecutar pytest, build de frontend e imports; reportar fallos.

## Riesgos / mitigaciones
- **Conflictos de archivos en paralelo:** mitigado con fases y propiedad disjunta de archivos.
- **Migración en Postgres (Railway):** la migración se crea pero NO se aplica automáticamente contra prod; se revisa antes.
- **Inferencia de nivel con pocos datos de Strava:** el plan usa defaults conservadores por distancia si faltan datos de nat./bici.

## Criterio de éxito
- Crear un objetivo de triatlón genera un plan multideporte coherente con semanas que empiezan en lunes y se ven bien en el calendario (sin desfase).
- Goggins puede reprogramar/escalar el plan desde el chat y razona con datos reales de Strava.
- Series y disciplinas se ven claras en escritorio y móvil.
- pytest y build de frontend pasan.
