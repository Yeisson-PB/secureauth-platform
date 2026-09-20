# SecureAuth Platform — Progress Tracker

> Este archivo es la fuente de verdad del avance del proyecto. Se actualiza al completar cada tarea principal. Las tareas ad-hoc (fixes puntuales, mantenimiento de dependencias, issues de seguridad menores, etc.) **no se registran aquí** — solo las 22 tareas principales del roadmap.

---

## 📍 Estado actual

- **Última tarea completada:** Task 13 (MFA con TOTP)
- **Próxima tarea:** Task 14 (OAuth2 con Google)
- **Módulo:** 14 de 22

---

## ✅ Tareas completadas (1–13)

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
  Validación de llaves PEM, utilidades de seguridad (bcrypt, generación de tokens, SHA-256, comparación constant-time). `MAX_LOGIN_ATTEMPTS` y `LOCKOUT_DURATION_SECONDS` ya existían en `Settings` desde esta tarea, pero no se usaban hasta Task 12.

- [x] **Task 6** — Modelos de base de datos y migraciones con Alembic
  Modelos async de SQLAlchemy: users, sessions, refresh_tokens, mfa_recovery_codes, audit_logs. `failed_login_attempts` y `locked_until` ya existían en `User` desde esta tarea.

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

- [x] **Task 12** — Detección de fuerza bruta y bloqueo progresivo
  Cierra el ciclo de brute-force protection que quedó pendiente desde Task 5/6: `AuthService.login()` ahora sí llama a `UserRepository.lock_user()` cuando `failed_login_attempts` alcanza `settings.MAX_LOGIN_ATTEMPTS` (5), fijando `locked_until = now + settings.LOCKOUT_DURATION_SECONDS` (15 min). El intento que provoca el bloqueo devuelve `403 account_locked` en vez del genérico `401 invalid_credentials` — decisión de seguridad explícita: se acepta el leak de "este email existe" a cambio de que el dueño legítimo de la cuenta entienda por qué su password correcto dejó de funcionar (mismo tipo de trade-off enumeración-vs-usabilidad que 404-sobre-403 en sessions, resuelto en la dirección contraria aquí porque el público objetivo — el dueño de la cuenta — se beneficia más de la claridad).
  🐛 Bugs corregidos antes de implementar:
  - `AuthService.login()` incrementaba `failed_login_attempts` en cada password incorrecto desde Task 8, pero nunca comparaba el conteo contra `MAX_LOGIN_ATTEMPTS` ni llamaba a `lock_user()` — el bloqueo de 15 minutos nunca ocurría en la práctica pese a que la infraestructura (columnas, config) ya existía.
  - `UserRepository.increment_failed_login_attempts()` hacía read-modify-write en Python (leer el conteo, sumar 1 en memoria, escribir) en vez de un `UPDATE` atómico — dos requests de login fallidos concurrentes podían leer el mismo valor inicial y perder un incremento entre sí, permitiendo a un atacante corriendo requests en paralelo hacer más intentos de los que `MAX_LOGIN_ATTEMPTS` debería permitir antes de activar el bloqueo. Corregido con `UPDATE ... SET failed_login_attempts = failed_login_attempts + 1 RETURNING ...`.
  - Se identificó (antes de que llegara a producción) un tercer problema de diseño: si al expirar la ventana de bloqueo no se resetea el contador, el primer password incorrecto después de esos 15 minutos suma sobre el conteo viejo y re-bloquea la cuenta de inmediato — un usuario legítimo que se equivoca una sola vez al escribir su password quedaría efectivamente bloqueado para siempre. Resuelto detectando en `login()` cuando `locked_until` ya pasó y llamando a `reset_failed_attempts()` antes de evaluar el intento actual.

- [x] **Task 13** — MFA con TOTP (activación, verificación, códigos de recuperación)
  Ciclo completo de MFA con `pyotp`, en un **login de dos pasos** (patrón Auth0/Okta/Google, elegido explícitamente sobre un único endpoint con `totp_code` opcional): `POST /auth/login` con password correcto y `mfa_enabled=True` devuelve un `mfa_token` temporal (`MFARequiredResponse`) en vez del token pair; `POST /auth/mfa/verify` intercambia ese `mfa_token` + un código TOTP o recovery code por el token pair real.
  - **Nuevo módulo `MFAService`** (`app/modules/auth/mfa_service.py`), separado de `AuthService` por responsabilidad (enrollment + recovery codes) aunque reutiliza `AuthService.create_mfa_token`/`decode_mfa_token` y `_issue_token_pair` en vez de duplicar la lógica de emisión de tokens/sesión.
  - **Enrollment en dos pasos:** `POST /auth/mfa/enable` genera y guarda un secreto TOTP (sin activar `mfa_enabled` todavía) y devuelve `otpauth_uri` + secreto en texto plano para entrada manual; `POST /auth/mfa/enable/confirm` exige un código válido contra ese secreto antes de activar `mfa_enabled` y emitir un lote de recovery codes — que se muestran **una sola vez** en la respuesta.
  - **`mfa_token` de un solo uso vía el blacklist de Redis existente (Task 9):** el JWT temporal usa `type: "mfa_pending"` (rechazado por `decode_access_token`/`get_current_user` si alguien lo manda como Bearer) y su `jti` se blacklistea inmediatamente al verificar con éxito, para que no pueda reutilizarse aunque no haya expirado. No se blacklistea en un intento fallido, para permitir reintentos dentro de la ventana corta del token.
  - **Recovery codes hasheados con SHA-256** (mismo enfoque que refresh tokens, no bcrypt — son strings de alta entropía generados por el sistema, no passwords de usuario). Se normalizan (mayúsculas, sin guiones/espacios) antes de hashear, tanto al generarlos como al verificarlos, para tolerar variaciones de formato al escribirlos manualmente. Se marcan como usados (`is_used=True`), nunca se borran — mismo principio de auditoría que los refresh tokens revocados.
  - **Desactivar MFA exige password Y código TOTP activo** (`POST /auth/mfa/disable`), no solo una sesión autenticada — así un access token robado nunca alcanza para apagar el segundo factor. Al desactivar, se invalidan todos los recovery codes pendientes.
  🐛 Bug corregido antes de implementar:
  - `app/core/config.py` definía el campo como `MFA_ISSUER`, pero `.env.example` documentaba (y sigue documentando) la variable como `MFA_ISSUER_NAME`. Con `case_sensitive=True` en `pydantic-settings`, la variable de entorno nunca llegaba al campo — cualquiera que configurara `MFA_ISSUER_NAME=MiEmpresa` seguía viendo "SecureAuth" como issuer en el authenticator de sus usuarios, sin ningún error visible. Corregido renombrando el campo en `Settings` a `MFA_ISSUER_NAME` (se trató `.env.example` como la fuente de verdad, no al revés, siguiendo el mismo criterio que en Task 9).
  ⚠️ Trade-off aceptado explícitamente: `POST /auth/mfa/verify` no tiene un bloqueo específico de intentos fallidos (a diferencia del login por password en Task 12) — se apoya en el rate limiting global por IP (Task 11) como única barrera contra fuerza bruta sobre el código TOTP de 6 dígitos. Dado que el `mfa_token` expira en `MFA_TOKEN_EXPIRE_MINUTES` (5 min por defecto) y el rate limiter ya limita requests por IP, se consideró suficiente por ahora; candidato a revisar en Task 20 (suite de tests de seguridad) si se quiere un límite dedicado.

---

## ⏳ Tareas pendientes (14–22)

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

- **JWT:** firmado con RS256 (asimétrico), nunca HS256. Desde Task 10 incluye el claim opcional `sid` (session id). Desde Task 13, un segundo tipo de JWT (`type: "mfa_pending"`) se usa exclusivamente como puente entre los dos pasos del login con MFA y nunca es válido como access token.
- **Refresh tokens:** se almacenan hasheados con SHA-256, nunca en texto plano.
- **Errores:** formato RFC 7807 (Problem Details) en todos los endpoints, incluyendo el 429 de rate limit y el 403 de account lockout.
- **Audit logs:** append-only, nunca se editan ni se borran.
- **Primary keys:** UUID en todos los modelos.
- **Capas:** router → service → repository → model, aplicado de forma consistente en todos los módulos de dominio. Desde Task 13, un dominio puede tener más de un service (`AuthService` + `MFAService`) cuando cubren responsabilidades claramente distintas dentro del mismo módulo, en vez de forzar todo en una sola clase creciente.
- **Estructura:** modular por dominio (auth, users, sessions, audit, admin).
- **Redis:** un único connection pool compartido (`app/core/redis_client.py`), nunca conexiones ad-hoc por request. Reutilizado por blacklist (Task 9), rate limiting (Task 11), y ahora por el single-use enforcement del `mfa_token` (Task 13).
- **Blacklist y rate limit fail-open:** si Redis está caído, tanto `is_token_blacklisted` como `check_rate_limit` devuelven el resultado "permitir" en vez de tumbar la API. Decisión explícita y documentada en código, no un descuido. Candidato a revisar (modo fail-closed configurable) en el hardening de seguridad (Task 20).
- **Revocación de sesión ≠ invalidación inmediata del access token:** revocar una sesión mata su refresh token, pero el access token ya emitido sigue vivo hasta expirar (máx. 15 min). Trade-off aceptado explícitamente.
- **404 sobre 403 en checks de ownership:** un recurso que no pertenece al usuario autenticado responde 404, nunca 403, para no confirmar la existencia de IDs ajenos.
- **Rate limiting sliding window, no fixed window:** implementado con Sorted Set + script Lua atómico, para evitar tanto el burst en el borde de la ventana como condiciones de carrera bajo concurrencia. Límite aplicado por IP siempre y por usuario autenticado adicionalmente.
- **Middleware de rate limiting desactivado en `APP_ENV=test`:** decisión explícita y documentada en `RateLimitMiddleware`, no un `if` escondido — necesaria porque el transporte ASGI de test no expone una IP real por request.
- **Bloqueo de cuenta revela existencia del email (403 account_locked), a diferencia de invalid_credentials genérico:** decisión explícita en Task 12. Se prioriza que el dueño legítimo entienda por qué su cuenta está bloqueada sobre ocultarle a un atacante que el email existe — resuelto en dirección opuesta al patrón 404-sobre-403 de sessions, con justificación documentada en el código.
- **Contador de intentos fallidos vía UPDATE atómico, no read-modify-write:** cualquier contador que gatille un control de seguridad (lockout, rate limit) debe incrementarse con una expresión SQL atómica (`columna = columna + 1`) para no ser vulnerable a race conditions bajo requests concurrentes.
- **MFA en dos pasos, no un único endpoint con código opcional (Task 13):** el password nunca se reenvía junto al código TOTP; el `mfa_token` intermedio tiene scope mínimo (no sirve como access token) y permite auditar/rate-limitar el paso de password y el paso de MFA como eventos independientes.
- **`mfa_token` de un solo uso:** se blacklistea en Redis inmediatamente tras una verificación exitosa, no se espera a su expiración natural — mismo mecanismo que el blacklist de logout (Task 9), reutilizado en vez de construir infraestructura paralela.
- **Recovery codes hasheados con SHA-256, no bcrypt:** son strings de alta entropía generados por el propio sistema (no passwords elegidos por el usuario), así que el enfoque de refresh tokens aplica directamente; se normalizan antes de hashear para tolerar variaciones de mayúsculas/guiones al transcribirlos.
- **Desactivar MFA exige password + TOTP, no solo sesión autenticada:** un access token robado nunca es suficiente por sí solo para apagar el segundo factor de la cuenta.

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
- **Contadores que gatillan controles de seguridad deben incrementarse atómicamente:** un patrón "SELECT, sumar en Python, UPDATE" en dos requests concurrentes puede perder incrementos (ambas leen el mismo valor de partida). Para un contador de intentos fallidos que alimenta un lockout, eso significa que un atacante con requests paralelos puede sobrepasar el límite configurado. La expresión SQL `columna = columna + 1` con `RETURNING` resuelve esto en un solo statement atómico, sin necesidad de un lock explícito ni una segunda query.
- **Resetear contadores de tiempo-limitado al detectar que la ventana expiró, no solo al tener éxito:** si un contador se resetea únicamente en el "camino feliz" (login exitoso), un usuario que falla una sola vez justo después de que su bloqueo anterior expiró vuelve a acumular sobre el conteo viejo y se re-bloquea de inmediato. Hay que detectar explícitamente "la ventana ya pasó" y resetear antes de evaluar el intento actual, no solo tras un éxito.
- **Nombres de variables de entorno deben coincidir EXACTAMENTE entre `Settings` y `.env.example`, y esto no se detecta solo:** con `case_sensitive=True`, un campo `Settings` mal nombrado respecto a `.env.example` no lanza ningún error — simplemente usa el valor por defecto silenciosamente, dando la falsa impresión de que la variable de entorno "no hace nada" en vez de señalar el typo. `MFA_ISSUER` vs `MFA_ISSUER_NAME` (Task 13) es el segundo bug de este tipo en el proyecto; vale la pena, en Task 20, agregar un test que itere sobre `.env.example` y confirme que cada variable ahí definida corresponde a un campo real de `Settings`.
- **Reutilizar infraestructura existente (blacklist de Redis) para un problema nuevo (single-use de un JWT intermedio) es más seguro que construir un mecanismo paralelo:** el `mfa_token` de Task 13 no necesitó una tabla nueva ni un TTL cache aparte — el mismo par `blacklist_token`/`is_token_blacklisted` de Task 9, indexado por `jti`, funciona igual de bien para "este token de MFA ya se usó" que para "este access token fue revocado por logout".
- **Separar un service en dos cuando las responsabilidades divergen, no solo cuando el archivo se pone largo:** `MFAService` se creó como clase aparte de `AuthService` no por tamaño de archivo, sino porque enrollment/recovery-codes es un concepto distinto de "emitir un JWT" — aunque ambos comparten la emisión final de tokens (`_issue_token_pair`), que se dejó como único punto de verdad para esa lógica en vez de duplicarla.

---

## 🗒️ Notas de sesión

_(Opcional: usa esta sección para dejar contexto rápido de dónde quedaste antes de cerrar una sesión de trabajo.)_

Task 13 cerrada: enrollment (`/mfa/enable` → `/mfa/enable/confirm`), login en dos pasos (`/login` → `/mfa/verify`), y `/mfa/disable` con password+TOTP. Antes de Task 14, correr `make test` completo con los archivos nuevos/modificados de esta tarea (`app/core/config.py`, `app/core/security.py`, `app/modules/auth/schemas.py`, `app/modules/auth/repository.py`, `app/modules/auth/service.py`, `app/modules/auth/mfa_service.py` nuevo, `app/modules/auth/router.py`, `.env.example`, `tests/modules/auth/test_mfa.py` nuevo) copiados sobre el repo real — en particular confirmar que el rename de `MFA_ISSUER` a `MFA_ISSUER_NAME` no rompe ningún `.env` local que alguien ya tuviera configurado con el nombre viejo (no debería, porque el campo viejo nunca funcionó, pero vale la pena verificarlo explícitamente). Para Task 14 (OAuth2 con Google), `Settings` ya tiene `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` y la propiedad `google_oauth_enabled` desde Task 5 — falta todo el flujo real: `GET /auth/oauth/google` (redirect a Google), `GET /auth/oauth/google/callback` (intercambio de code por tokens, creación/vinculación de `User` con `oauth_provider="google"` + `oauth_provider_id`), y decidir qué pasa si el email de Google ya existe como cuenta local con password (¿se vincula automáticamente, o se rechaza y se pide iniciar sesión con password primero para vincular explícitamente?). Esa decisión de vinculación de cuentas es la primera que hay que tomar al arrancar Task 14, en la misma línea que la decisión de flujo de MFA se tomó antes de escribir código en Task 13.
