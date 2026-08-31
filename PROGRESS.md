# SecureAuth Platform — Progress Tracker

> Este archivo es la fuente de verdad del avance del proyecto. Se actualiza al completar cada tarea principal. Las tareas ad-hoc (fixes puntuales, mantenimiento de dependencias, issues de seguridad menores, etc.) **no se registran aquí** — solo las 22 tareas principales del roadmap.

---

## 📍 Estado actual

- **Última tarea completada:** Task 10 (Gestión de sesiones activas)
- **Próxima tarea:** Task 11 (Rate limiting por IP y por usuario)
- **Módulo:** 11 de 22

---

## ✅ Tareas completadas (1–10)

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

---

## ⏳ Tareas pendientes (11–22)

- [ ] **Task 11** — Rate limiting por IP y por usuario (sliding window en Redis)
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
- **Errores:** formato RFC 7807 (Problem Details) en todos los endpoints.
- **Audit logs:** append-only, nunca se editan ni se borran.
- **Primary keys:** UUID en todos los modelos.
- **Capas:** router → service → repository → model, aplicado de forma consistente en todos los módulos de dominio (incluyendo el nuevo `sessions`).
- **Estructura:** modular por dominio (auth, users, sessions, audit, admin).
- **Redis:** un único connection pool compartido (`app/core/redis_client.py`), nunca conexiones ad-hoc por request. Blacklist de tokens con TTL = tiempo de vida restante del access token.
- **Blacklist fail-open:** si Redis está caído, `is_token_blacklisted` devuelve `False` (se permite la request) para no tumbar toda la autenticación por una caída de Redis. Es una decisión explícita, documentada en código — no un descuido. Revisar si un modo fail-closed configurable por entorno debe añadirse en el hardening de seguridad (candidato para Task 20).
- **Revocación de sesión ≠ invalidación inmediata del access token:** revocar una sesión mata su refresh token, pero el access token ya emitido sigue vivo hasta expirar (máx. 15 min). Trade-off aceptado explícitamente para no acoplar el módulo `sessions` a un mapeo jti↔session en Redis sin necesidad probada. Candidato a revisar en Task 20 si se requiere revocación instantánea.
- **404 sobre 403 en checks de ownership:** tanto en `DELETE /sessions/{id}` (Task 10) como en el resto de la API, un recurso que no pertenece al usuario autenticado responde 404, nunca 403, para no confirmar la existencia de IDs ajenos.

---

## 📚 Aprendizajes técnicos

- **Docker + UV:** nunca copiar `.venv` entre stages de un build multi-stage (rompe por paths absolutos). Usar `uv export --frozen --no-dev --no-hashes -o requirements.txt` en el builder stage, e instalar con pip en el runtime stage.
- **UV 0.4.20:** `default-groups` bajo `[tool.uv]` no está disponible en esta versión; usar el flag CLI `--group dev` como fallback seguro (por ejemplo, en `docker-compose.test.yml`).
- **Hatchling:** requiere que `README.md` esté presente en el contexto de build al resolver metadata de `pyproject.toml` durante instalaciones editables.
- **Rotación de refresh tokens:** si un token ya usado se reintenta usar, se interpreta como robo y se revocan TODOS los tokens del usuario (fail-secure).
- **Redis en `get_current_user`:** si Redis está caído, se falla "open" (se permite la request) por disponibilidad. Decisión documentada explícitamente en `app/core/redis_client.py` desde Task 9.
- **SQLAlchemy declarative `Base`:** `metadata` es un nombre de atributo reservado por la clase base (`Base.metadata`). Los modelos ORM y el código que los instancia deben usar nombres de campo que no choquen con esto — en `AuditLog` el atributo Python se llama `context` aunque la columna DB se siga llamando `metadata`.
- **Bugs silenciosos por falta de cobertura de tests de integración:** un método inexistente (`_blacklist_access_token`) pasó desapercibido varias tareas porque ningún test hacía login → logout → intento de reuso del token. Regla general: todo flujo de seguridad crítico (login, logout, revocación) necesita un test que ejecute el flujo completo de punta a punta, no solo el "happy path" de cada endpoint por separado.
- **Parseo de User-Agent sin dependencias externas:** el orden de los patrones de regex importa — UAs de Edge/Opera/Chrome-iOS contienen "Safari" y/o "Chrome" como substrings, así que los tokens más específicos (`Edg/`, `OPR/`, `CriOS/`) deben evaluarse antes que los genéricos (`Chrome/`, `Version/.*Safari`) o el resultado queda mal clasificado.
- **JWT con claims opcionales:** agregar `sid` al payload del access token en Task 10 se hizo de forma retrocompatible (`sid: str | None = None` en `TokenPayload`) — tokens emitidos antes de este cambio simplemente no lo tendrán, y el código que lo consume (`get_current_session_id`) maneja su ausencia sin fallar.

---

## 🗒️ Notas de sesión

_(Opcional: usa esta sección para dejar contexto rápido de dónde quedaste antes de cerrar una sesión de trabajo, por ejemplo "quedé revisando el TTL del blacklist, falta decidir si usar el exp del JWT o un valor fijo".)_

Task 10 cerrada. Antes de Task 11, confirmar en local que `make test` pasa completo con los archivos nuevos/modificados de sesiones (`app/core/user_agent.py`, `app/modules/sessions/*`, `app/modules/auth/repository.py`, `app/modules/auth/service.py`, `app/modules/auth/dependencies.py`, `app/modules/auth/schemas.py`, `app/api/v1/router.py`, `tests/modules/sessions/*`) copiados sobre el repo real. Para Task 11 (rate limiting), reutilizar `app/core/redis_client.py` en vez de abrir otra conexión Redis independiente — mismo patrón que blacklist.
