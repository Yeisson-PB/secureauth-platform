# SecureAuth Platform — Progress Tracker

> Este archivo es la fuente de verdad del avance del proyecto. Se actualiza al completar cada tarea principal. Las tareas ad-hoc (fixes puntuales, mantenimiento de dependencias, issues de seguridad menores, etc.) **no se registran aquí** — solo las 22 tareas principales del roadmap.

---

## 📍 Estado actual

- **Última tarea completada:** Task 11 (Rate limiting por IP y por usuario)
- **Próxima tarea:** Task 12 (Detección de fuerza bruta y bloqueo progresivo)
- **Módulo:** 12 de 22

---

## ✅ Tareas completadas (1–11)

- [x] **Task 1** — Estructura base del repositorio y configuración inicial
  Estructura modular por dominio, configuración de UV, pre-commit hooks.

- [x] **Task 2** — Docker Compose completo (FastAPI + PostgreSQL + Redis)
  Multi-stage Dockerfile, healthchecks, Makefile.
  ⚠️ Aprendizaje clave: no se puede copiar `.venv` entre stages de Docker (paths absolutos rotos). Solución: `uv export` → `requirements.txt` → `pip install` en el stage de runtime.

- [x] **Task 3** — README profesional con diagrama de arquitectura en Mermaid
  Diagramas de arquitectura y de flujo de autenticación (sequence diagram).

- [x] **Task 4** — GitHub Actions: pipeline CI con Bandit + Semgrep + Pytest
  Lint, SAST (Bandit/Semgrep), tests, build de Docker, escaneo semanal de CVEs (pip-audit), Gitleaks en PRs.

- [x] **Task 5** — Configuración de variables de entorno con Pydantic Settings
  Validación de llaves PEM, utilidades de seguridad (bcrypt, generación de tokens, SHA-256, comparación constant-time).

- [x] **Task 6** — Modelos de base de datos y migraciones con Alembic
  Modelos async de SQLAlchemy: users, sessions, refresh_tokens, mfa_recovery_codes, audit_logs.

- [x] **Task 7** — Módulo de usuarios: registro y validación de inputs
  Endpoint de registro con validación de fuerza de contraseña y normalización de email.

- [x] **Task 8** — Módulo de autenticación: login + JWT (RS256) + refresh tokens
  Login con JWT RS256, rotación de refresh tokens con detección de robo, dependency `get_current_user`.

- [x] **Task 9** — Blacklist de tokens en Redis y logout seguro
  Cliente Redis centralizado (`app/core/redis_client.py`) con connection pool reutilizable, helpers `blacklist_token` / `is_token_blacklisted` con semántica fail-open documentada explícitamente, y cierre limpio del pool vía lifespan handler en `app/main.py`.
  🐛 Bugs corregidos:
  - `AuthService.logout()` llamaba a un método inexistente (`_blacklist_access_token` en vez de `_blacklist_token`), causando `AttributeError` en cada logout en producción. El blacklist nunca se escribía.
  - `AuditLog(...)` recibía `metadata=` como kwarg del constructor — nombre reservado por `Base.metadata` de SQLAlchemy declarative. Corregido a `context=` (el nombre real del atributo del modelo; la columna DB sigue llamándose `metadata`).
  - Tests nuevos (`tests/modules/auth/test_blacklist.py`) cubren login → logout → reintento de reuso del access/refresh token, que antes no se probaba de punta a punta y por eso el bug pasó desapercibido.

- [x] **Task 10** — Gestión de sesiones activas (listar, revocar por dispositivo)
  Nuevo módulo `sessions` (router → service → repository, siguiendo el patrón de capas ya establecido): `GET /sessions` lista dispositivos conectados, `DELETE /sessions/{id}` revoca uno específico. Parser de User-Agent sin dependencias (`app/core/user_agent.py`) que ahora sí puebla `device_name`, `device_type`, `browser`, `os` en cada sesión — antes quedaban siempre en `NULL`. El JWT de acceso ahora incluye el claim `sid` (session id), lo que permite marcar `is_current: true` en el listado. Revocar una sesión invalida su refresh token (`AuthRepository.revoke_refresh_tokens_by_session`) pero **no** el access token ya emitido para esa sesión, que sigue vigente hasta su expiración natural (máx. 15 min) — misma filosofía fail-open documentada en Task 9, ahora aplicada aquí también. Validación de ownership devuelve 404 (no 403) para no filtrar existencia de sesiones ajenas.

- [x] **Task 11** — Rate limiting por IP y por usuario (sliding window en Redis)
  Middleware global (`app/core/rate_limit_middleware.py`) que corre en cada request (salvo `/health`, `/docs`, `/redoc`, `/openapi.json`) sin necesidad de aplicarlo endpoint por endpoint. Algoritmo sliding window log implementado con un Sorted Set de Redis y un script Lua ejecutado atómicamente vía `EVAL` (`app/core/rate_limiter.py`) — evita tanto el "burst" del fixed window en el borde de la ventana como una condición de carrera (TOCTOU) bajo requests concurrentes. Aplica el límite por IP siempre, y adicionalmente por usuario autenticado (extraído del JWT) cuando hay un Bearer token válido presente. Fail-open si Redis está caído, mismo criterio que Task 9/10. El middleware se desactiva automáticamente en entorno de test (`settings.is_test`) porque el transporte ASGI de test comparte una sola IP entre toda la suite; el comportamiento del rate limiting se cubre con tests dedicados (`tests/core/`) que prueban el algoritmo directamente y el middleware sobre una mini-app Starlette aislada. `CORSMiddleware` se agrega después de `RateLimitMiddleware` para quedar como capa más externa, así las respuestas 429 también llevan headers CORS correctos.
  🐛 Bug corregido:
  - `_extract_user_id()` en `rate_limit_middleware.py` asumía que el header `Authorization`
    siempre era un string y llamaba `.startswith()` directamente sobre el resultado de
    `request.headers.get(...)`, que es `None` cuando el header no está presente →
    `AttributeError` en cada request sin token. Corregido con `if not auth_header or not auth_header.startswith(...)`.
  - Tests de `tests/core/` corrían contra Redis real y compartían pool + claves entre
    tests, causando dos fallas intermitentes: (a) pool de conexión ligado al event loop
    de un test anterior (`pytest-asyncio` crea un loop nuevo por test función), causando
    `RuntimeError: Event loop is closed` y activando fail-open silenciosamente; (b)
    claves `ratelimit:*` no se limpiaban entre tests, así que contadores de un test
    contaminaban el siguiente. Corregido con fixture `autouse` en `tests/core/conftest.py`
    que cierra el pool y hace flush de claves `ratelimit:*` antes/después de cada test.

---

## ⏳ Tareas pendientes (12–22)

- [ ] **Task 12** — Detección de fuerza bruta y bloqueo progresivo
- [ ] **Task 13** — MFA con TOTP (activación, verificación, códigos de recuperación)
- [ ] **Task 14** — OAuth2 con Google
- [ ] **Task 15** — OAuth2 con GitHub
- [ ] **Task 16** — Headers de seguridad globales y configuración de CORS
- [ ] **Task 17** — Audit logs inmutables (append-only)
- [ ] **Task 18** — Módulo de administración: gestión de usuarios, sesiones y logs
- [ ] **Task 19** — Swagger/OpenAPI completo con ejemplos en todos los endpoints
- [ ] **Task 20** — Suite de tests de seguridad automatizados
- [ ] **Task 21** — Docker Compose de producción con Nginx como reverse proxy + SSL
- [ ] **Task 22** — Guía de integración: cómo conectar SecureAuth a cualquier app externa

---

## 🏗️ Decisiones de arquitectura clave (no negociables)

- **JWT:** firmado con RS256 (asimétrico), nunca HS256. Desde Task 10 incluye el claim opcional `sid` (session id).
- **Refresh tokens:** se almacenan hasheados con SHA-256, nunca en texto plano.
- **Errores:** formato RFC 7807 (Problem Details) en todos los endpoints, incluyendo el 429 de rate limit.
- **Audit logs:** append-only, nunca se editan ni se borran.
- **Primary keys:** UUID en todos los modelos.
- **Capas:** router → service → repository → model, aplicado de forma consistente en todos los módulos de dominio.
- **Estructura:** modular por dominio (auth, users, sessions, audit, admin).
- **Redis:** un único connection pool compartido (`app/core/redis_client.py`), nunca conexiones ad-hoc por request. Reutilizado por blacklist (Task 9) y por rate limiting (Task 11).
- **Blacklist y rate limit fail-open:** si Redis está caído, tanto `is_token_blacklisted` como `check_rate_limit` devuelven el resultado "permitir" en vez de tumbar la API. Decisión explícita y documentada en código, no un descuido. Candidato a revisar (modo fail-closed configurable) en el hardening de seguridad (Task 20).
- **Revocación de sesión ≠ invalidación inmediata del access token:** revocar una sesión mata su refresh token, pero el access token ya emitido sigue vivo hasta expirar (máx. 15 min). Trade-off aceptado explícitamente.
- **404 sobre 403 en checks de ownership:** un recurso que no pertenece al usuario autenticado responde 404, nunca 403, para no confirmar la existencia de IDs ajenos.
- **Rate limiting sliding window, no fixed window:** implementado con Sorted Set + script Lua atómico, para evitar tanto el burst en el borde de la ventana como condiciones de carrera bajo concurrencia. Límite aplicado por IP siempre y por usuario autenticado adicionalmente.
- **Middleware de rate limiting desactivado en `APP_ENV=test`:** decisión explícita y documentada en `RateLimitMiddleware`, no un `if` escondido — necesaria porque el transporte ASGI de test no expone una IP real por request.

---

## 📚 Aprendizajes técnicos

- **Docker + UV:** nunca copiar `.venv` entre stages de un build multi-stage (rompe por paths absolutos). Usar `uv export --frozen --no-dev --no-hashes -o requirements.txt` en el builder stage, e instalar con pip en el runtime stage.
- **UV 0.4.20:** `default-groups` bajo `[tool.uv]` no está disponible en esta versión; usar el flag CLI `--group dev` como fallback seguro (por ejemplo, en `docker-compose.test.yml`).
- **Hatchling:** requiere que `README.md` esté presente en el contexto de build al resolver metadata de `pyproject.toml` durante instalaciones editables.
- **Rotación de refresh tokens:** si un token ya usado se reintenta usar, se interpreta como robo y se revocan TODOS los tokens del usuario (fail-secure).
- **Redis en `get_current_user`:** si Redis está caído, se falla "open" (se permite la request) por disponibilidad. Decisión documentada explícitamente en `app/core/redis_client.py` desde Task 9.
- **SQLAlchemy declarative `Base`:** `metadata` es un nombre de atributo reservado por la clase base (`Base.metadata`). Los modelos ORM y el código que los instancia deben usar nombres de campo que no choquen con esto — en `AuditLog` el atributo Python se llama `context` aunque la columna DB se siga llamando `metadata`.
- **Bugs silenciosos por falta de cobertura de tests de integración:** un método inexistente (`_blacklist_access_token`) pasó desapercibido varias tareas porque ningún test hacía login → logout → intento de reuso del token. Regla general: todo flujo de seguridad crítico necesita un test que ejecute el flujo completo de punta a punta.
- **Parseo de User-Agent sin dependencias externas:** el orden de los patrones de regex importa — UAs de Edge/Opera/Chrome-iOS contienen "Safari" y/o "Chrome" como substrings, así que los tokens más específicos deben evaluarse antes que los genéricos.
- **JWT con claims opcionales:** agregar `sid` al payload del access token en Task 10 se hizo de forma retrocompatible (`sid: str | None = None`).
- **Sliding window con Redis:** un fixed window (contador con `INCR` + `EXPIRE`) permite hasta 2x el límite en el borde de la ventana. Un Sorted Set con timestamps como score, podado en cada chequeo con `ZREMRANGEBYSCORE`, no tiene ese problema. El chequeo completo (podar + contar + agregar) debe ser atómico vía script Lua (`EVAL`), o dos requests concurrentes pueden ambas pasar el límite antes de que ninguna escriba.
- **Testing de middlewares con estado compartido (Redis, rate limit):** cuando toda la suite de tests comparte una sola "identidad" de red (una IP falsa del transporte ASGI), un middleware de rate limiting global rompe tests no relacionados si no se desactiva explícitamente en entorno de test. La solución no es "no testear el middleware", sino aislar sus tests en una mini-app dedicada con límites propios.
- **Tests contra Redis real necesitan limpieza explícita de estado:** un mock hubiera
  evitado esto, pero al usar Redis real en tests (`tests/core/`) dos problemas de
  aislamiento son fáciles de pasar por alto: (1) un pool de conexión singleton reutilizado
  entre tests con event loops distintos (uno por test función en pytest-asyncio) revienta
  con "Event loop is closed"; (2) las claves escritas por un test persisten en Redis y
  contaminan el siguiente si comparten el mismo key pattern (en este caso, todos los tests
  de middleware pegan a la misma IP falsa del transporte ASGI). Regla general: cualquier
  test suite que hable con Redis real necesita un fixture `autouse` que resetee tanto la
  conexión como el keyspace relevante antes de cada test, sin importar el orden de ejecución.

---

## 🗒️ Notas de sesión

_(Opcional: usa esta sección para dejar contexto rápido de dónde quedaste antes de cerrar una sesión de trabajo, por ejemplo "quedé revisando el TTL del blacklist, falta decidir si usar el exp del JWT o un valor fijo".)_

Task 11 cerrada. Antes de Task 12, confirmar en local que `make test` pasa completo con los archivos nuevos/modificados (`app/core/rate_limiter.py`, `app/core/rate_limit_middleware.py`, `app/main.py`, `tests/core/*`) copiados sobre el repo real. Para Task 12 (fuerza bruta y bloqueo progresivo), el modelo `User` ya tiene `failed_login_attempts` y `locked_until`, y `AuthService.login()` ya incrementa `failed_login_attempts` en cada password incorrecto — pero nunca llama a `lock_user()` para fijar `locked_until` cuando se supera `MAX_LOGIN_ATTEMPTS`. Esa es la pieza que falta cerrar en Task 12, reutilizando `settings.MAX_LOGIN_ATTEMPTS` y `settings.LOCKOUT_DURATION_SECONDS` que ya existen en la configuración desde Task 5.
