# SecureAuth Platform — Progress Tracker

> Este archivo es la fuente de verdad del avance del proyecto. Se actualiza al completar cada tarea principal. Las tareas ad-hoc (fixes puntuales, mantenimiento de dependencias, issues de seguridad menores, etc.) **no se registran aquí** — solo las 22 tareas principales del roadmap.

---

## 📍 Estado actual

- **Última tarea completada:** Task 9 (Blacklist de tokens en Redis y logout seguro)
- **Próxima tarea:** Task 10 (Gestión de sesiones activas)
- **Módulo:** 10 de 22

---

## ✅ Tareas completadas (1–9)

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
+ - 🔒 **Vulnerabilidad corregida en `app/core/config.py`:** `validate_pem_keys` sustituía silenciosamente una `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` mal formada por el contenido de `keys/*.pem` en disco si ese archivo existía — incluso cuando la variable de entorno traía un valor inválido. En producción esto significaba que un typo en `.env` podía hacer arrancar la app silenciosamente con una clave RSA distinta a la esperada, sin ningún error. Ahora una clave con header PEM inválido siempre falla la validación (fail loud), sin importar si existe fallback en disco. El fallback a disco solo aplica cuando la variable está completamente ausente/vacía (uso legítimo en desarrollo local). Detectado gracias a que `test_invalid_pem_keys_raise` empezó a fallar al correr `make test` con las claves de test ya generadas en disco.
+ ✅ **Verificada end-to-end:** `make test` corre 58/58 tests en verde con 83.86% de cobertura (umbral mínimo: 80%).

---

## ⏳ Tareas pendientes (10–22)

- [ ] **Task 10** — Gestión de sesiones activas (listar, revocar por dispositivo)
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

- **JWT:** firmado con RS256 (asimétrico), nunca HS256.
- **Refresh tokens:** se almacenan hasheados con SHA-256, nunca en texto plano.
- **Errores:** formato RFC 7807 (Problem Details) en todos los endpoints.
- **Audit logs:** append-only, nunca se editan ni se borran.
- **Primary keys:** UUID en todos los modelos.
- **Capas:** router → service → repository → model, aplicado de forma consistente en todos los módulos de dominio.
- **Estructura:** modular por dominio (auth, users, sessions, audit, admin).
- **Redis:** un único connection pool compartido (`app/core/redis_client.py`), nunca conexiones ad-hoc por request. Blacklist de tokens con TTL = tiempo de vida restante del access token.
- **Blacklist fail-open:** si Redis está caído, `is_token_blacklisted` devuelve `False` (se permite la request) para no tumbar toda la autenticación por una caída de Redis. Es una decisión explícita, documentada en código — no un descuido. Revisar si un modo fail-closed configurable por entorno debe añadirse en el hardening de seguridad (candidato para Task 20).

---

## 📚 Aprendizajes técnicos

- **Docker + UV:** nunca copiar `.venv` entre stages de un build multi-stage (rompe por paths absolutos). Usar `uv export --frozen --no-dev --no-hashes -o requirements.txt` en el builder stage, e instalar con pip en el runtime stage.
+ **UV — versión fijada:** el Dockerfile fijaba `ghcr.io/astral-sh/uv:0.4.20`, versión donde `default-groups` bajo `[tool.uv]` no existe como opción válida (falla el parseo del TOML). Se actualizó la versión fijada a `0.12.5` (reproducible, no `latest`) tras confirmar compatibilidad. Se mantiene el flag CLI explícito `--group dev` en `docker-compose.test.yml` en vez de `default-groups`, por ser más explícito y no depender de comportamiento implícito de `uv run`.
+ **Entorno de test en Docker — código fuente necesario en el builder stage:** `docker-compose.test.yml` no monta ningún volumen con el código fuente para `api_test`, así que el stage `builder` del Dockerfile necesita copiar explícitamente `README.md` (requerido por Hatchling para instalaciones editables) y el código completo (`app/`, `tests/`, `alembic/`, `alembic.ini`) — no solo `pyproject.toml`/`uv.lock` como bastaba cuando ese stage solo generaba `requirements.txt`.
+ **Claves RS256 efímeras para test:** se generan con `openssl` directamente en el `command` de `docker-compose.test.yml` y se exportan como variables de entorno (`JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`) antes de correr pytest — igual que ya hacía `.github/workflows/ci.yml`. Nunca se depende únicamente del fallback a archivo en disco de `config.py` (ver vulnerabilidad corregida en Task 9).
+ **`coverage.xml` como bind mount de Docker:** si el archivo no existe en el host antes de `docker compose up`, Docker crea automáticamente un *directorio* vacío en su lugar en vez de fallar, rompiendo la escritura del reporte de cobertura (`IsADirectoryError`). El `Makefile` ahora ejecuta `touch coverage.xml` antes de levantar el entorno de test.
- **Hatchling:** requiere que `README.md` esté presente en el contexto de build al resolver metadata de `pyproject.toml` durante instalaciones editables.
- **Rotación de refresh tokens:** si un token ya usado se reintenta usar, se interpreta como robo y se revocan TODOS los tokens del usuario (fail-secure).
- **Redis en `get_current_user`:** si Redis está caído, se falla "open" (se permite la request) por disponibilidad. Decisión documentada explícitamente en `app/core/redis_client.py` desde Task 9.
- **SQLAlchemy declarative `Base`:** `metadata` es un nombre de atributo reservado por la clase base (`Base.metadata`). Los modelos ORM y el código que los instancia deben usar nombres de campo que no choquen con esto — en `AuditLog` el atributo Python se llama `context` aunque la columna DB se siga llamando `metadata`.
- **Bugs silenciosos por falta de cobertura de tests de integración:** un método inexistente (`_blacklist_access_token`) pasó desapercibido varias tareas porque ningún test hacía login → logout → intento de reuso del token. Regla general: todo flujo de seguridad crítico (login, logout, revocación) necesita un test que ejecute el flujo completo de punta a punta, no solo el "happy path" de cada endpoint por separado.

---

## 🗒️ Notas de sesión

_(Opcional: usa esta sección para dejar contexto rápido de dónde quedaste antes de cerrar una sesión de trabajo, por ejemplo "quedé revisando el TTL del blacklist, falta decidir si usar el exp del JWT o un valor fijo".)_

Task 9 cerrada. Antes de Task 10, confirmar en local que `make test` pasa completo con los archivos nuevos (`app/core/redis_client.py`, `app/modules/auth/service.py`, `app/modules/auth/dependencies.py`, `app/main.py`, `tests/modules/auth/test_blacklist.py`) copiados sobre el repo real.
