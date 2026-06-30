# Sistema de usuarios, contraseñas y maestro

**Fecha:** 2026-06-30
**Rama:** `feature/auth-users`
**Objetivo:** autenticación con email/contraseña, aislamiento de datos por usuario, un usuario maestro que ve todo, y vinculación de Strava por usuario.

## Estado actual (problema)
- `User` tiene `email` (único) y tokens de Strava por usuario, pero NO contraseña ni rol.
- Todas las rutas reciben `user_id` por la URL **sin autenticación** → cualquiera puede leer/escribir datos de cualquier `user_id`.
- Frontend con `USER_ID = 1` fijo en cada página.
- Sin librerías de auth en requirements.

## Decisiones aprobadas
1. **Sesión:** JWT (token Bearer en localStorage). Libs: `bcrypt` + `pyjwt`.
2. **Maestro:** el usuario actual (id=1, con todos los datos) se convierte en maestro: email `ikergalarza1999@gmail.com`, password `123456Iker` (hasheada), `is_master=true`.
3. **Vista maestro:** panel de administración (vista combinada) que lista todos los usuarios con resumen + crear usuario + "ver como" para entrar a los datos completos de cada uno.
4. **Alta:** solo el maestro crea usuarios (sin registro público).

## Backend
- **Modelo:** `User.hashed_password` (String), `User.is_master` (Boolean default False). `ensure_schema` añade ambas columnas.
- **services/auth.py:** `hash_password`, `verify_password` (bcrypt), `create_access_token`, `decode_token` (pyjwt; secreto `settings.JWT_SECRET`, expiración configurable ~30 días).
- **config.py:** `JWT_SECRET` (default de desarrollo), `JWT_EXPIRE_DAYS`.
- **api/deps.py:** `get_current_user` (lee Bearer), `require_master`, `authorize_user(user_id, current)` → permite si `current.is_master` o `current.id == user_id`, si no 403.
- **api/routes/auth.py:**
  - `POST /api/auth/login` {email, password} → {access_token, user}
  - `GET /api/auth/me` → usuario actual
  - `GET /api/auth/users` (solo maestro) → lista de usuarios con resumen (objetivos, nº workouts, strava_conectado, última actividad)
  - `POST /api/auth/users` (solo maestro) → crear usuario {name, email, password}
- **Protección de rutas existentes:** goals, plans, chat, strava, ai, records, profile pasan a exigir `get_current_user` y validar con `authorize_user(user_id, current)`. (Se mantiene `user_id` en la URL para minimizar el churn; la autorización es la que cierra el acceso.)
- **Seed maestro:** en el lifespan, tras `ensure_schema`: localizar usuario por email `ikergalarza1999@gmail.com` o id=1; fijar email, `hashed_password`, `is_master=true`. Si no existe ninguno, crearlo.

## Frontend
- **api.ts:** interceptor de request (añade `Authorization: Bearer <token>` desde localStorage) y de response (401 → limpia token y redirige a /login).
- **AuthContext:** `token`, `user`, `login(email, pwd)`, `logout()`, `loading`; al montar, si hay token hace `GET /me`. Expone `effectiveUserId` (el propio, o el seleccionado por el maestro al "ver como").
- **Login (/login):** email + contraseña, sin registro público.
- **App.tsx:** `AuthProvider`; guard (sin token → /login); ruta `/admin` solo maestro.
- **Páginas:** quitar `USER_ID = 1`; usar `effectiveUserId` del contexto (Activities, Chat, ActivityDetail, Goals, Plan, Dashboard, Records, Profile).
- **Admin (/admin):** lista de usuarios + crear usuario + "ver como" (fija `effectiveUserId`); banner "Viendo como X" cuando el maestro impersona.
- **Layout:** enlace Admin (solo maestro) + logout + banner de impersonación.
- **Strava:** ya es por usuario; el botón "Emparejar Strava" usa el `effectiveUserId`.

## Tests
- backend: hash/verify password, login OK/KO, get_current_user con token válido/ inválido, authorize_user (propio vs ajeno vs maestro), crear usuario solo-maestro, seed del maestro.

## Seguridad / notas
- Poner `JWT_SECRET` en Railway para producción (hay default solo para desarrollo).
- `123456Iker` es débil; recomendar cambiarla.
- Riesgo: romper el login deja fuera de producción → implementar en rama, verificar (pytest + build + arranque), luego merge a main.

## Criterio de éxito
- Login con el maestro funciona y ve sus datos actuales intactos.
- Un usuario normal solo ve/edita sus datos (403 si intenta otro id).
- El maestro crea usuarios y puede "ver como" cualquiera.
- Cada usuario vincula su propio Strava.
- pytest y build de frontend pasan.
