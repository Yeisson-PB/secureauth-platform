# SecureAuth Platform — Progress Tracker

> Este archivo es la fuente de verdad del avance del proyecto. Se actualiza al completar cada tarea principal. Las tareas ad-hoc (fixes puntuales, mantenimiento de dependencias, issues de seguridad menores, etc.) **no se registran aquí** — solo las 22 tareas principales del roadmap.

---

## 📍 Estado actual

- **Última tarea completada:** Task 8 (Authentication core: JWT + refresh tokens)
- **Próxima tarea:** Task 9 (Blacklist de tokens en Redis y logout seguro)
- **Módulo:** 9 de 22

---

## ✅ Tareas completadas (1–8)

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

---

## ⏳ Tareas pendientes (9–22)

- [ ] **Task 9** — Blacklist de tokens en Redis y logout seguro
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

---

## 📚 Aprendizajes técnicos

- **Docker + UV:** nunca copiar `.venv` entre stages de un build multi-stage (rompe por paths absolutos). Usar `uv export --frozen --no-dev --no-hashes -o requirements.txt` en el builder stage, e instalar con pip en el runtime stage.
- **Rotación de refresh tokens:** si un token ya usado se reintenta usar, se interpreta como robo y se revocan TODOS los tokens del usuario (fail-secure).
- **Redis en `get_current_user`:** si Redis está caído, actualmente se falla "open" (se permite la request) por disponibilidad. Revisar si esto se ajusta a un fail-closed en entornos de alta seguridad.

---

## 🗒️ Notas de sesión

_(Opcional: usa esta sección para dejar contexto rápido de dónde quedaste antes de cerrar una sesión de trabajo, por ejemplo "quedé revisando el TTL del blacklist, falta decidir si usar el exp del JWT o un valor fijo".)_
