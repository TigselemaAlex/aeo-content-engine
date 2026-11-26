# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Content Engine de AEO.co: app web interna donde el operador sube el video largo de un cliente y la herramienta genera 20 piezas (6 clips verticales, 4 carruseles, 6 posts, 1 blog AEO, 1 newsletter, 2 gráficos de cita) aplicando el Edit Spec de ese cliente. El operador revisa, corrige o regenera, y envía el paquete. Roles: `admin`, `operator`, `video_reviewer`.

## Estado

Monorepo con su esqueleto (T1.2): `apps/`, `packages/`, `supabase/` y `templates/` existen pero están vacías. `worker/` ya es un proyecto uv (T1.3) donde funcionan `uv run ruff check` (exige docstrings, reglas `D`), `uv run python -m pyright`, `uv run python -m pytest` (incluye los doctests de `src/`) y los comandos `uv run python -m content_engine hello`, `extract-audio`, `transcribe` (T1.4), `cut` (T1.6), `detect-faces` (T2.1) y `camera-path` (T2.2). En Windows se usa `python -m` porque el sistema puede bloquear los lanzadores `.exe` de uv (ver `worker/README.md`). De los comandos `pnpm` de abajo solo existen `pnpm lint` y `pnpm test`, y por ahora solo cubren el worker (Ruff, Pyright, import-linter y pytest); el resto se agrega en la tarea que crea lo que necesita. Repo público en GitHub con `main` protegida: todo cambio entra por rama y pull request, y el CI (`.github/workflows/ci.yml`, trabajo `worker`) tiene que pasar para fusionar.

**Progreso:** última tarea cerrada **T2.2b** (25 nov 2026) · siguiente **T2.3**. Registro completo en `docs/progreso.md`; al cerrar una tarea se agrega ahí una línea y se reemplaza esta.

## Dónde está el resto

Todo se carga desde aquí: **no** crees `CLAUDE.md` dentro de subcarpetas.

| Skill | Úsala para |
| --- | --- |
| `arquitectura` | Flujo de un video, estados, cola, módulos y sus tablas, Edit Spec efectivo, tipos de pieza como plugins |
| `interfaz` | Cualquier pantalla, componente o estilo de `apps/web` (paleta, Manrope, iconos Tabler, formas) |
| `tarea-del-plan` | Ejecutar una tarea `T*.*` de `docs/07` paso a paso y cerrar su progreso |
| `registrar-aprendizaje` | Guardar lo aprendido (de un agente, de una corrección de Alex o de un error) como barrera en código, regla o skill, sin contradecir lo ya escrito |

| Agente | Úsalo para |
| --- | --- |
| `revisor-de-codigo` | Revisar código contra las reglas del proyecto, al cerrar una tarea o antes de dar un cambio por terminado |
| `guardian-de-docs` | Ver si un cambio o decisión dejó los documentos incoherentes |
| `documentador` | Escribir o mejorar docstrings (Python y TypeScript). Es **el único** que los escribe: al crear o cambiar código, pásalo por él |
| `explicador` | Explicar código que no escribió, con números reales del tramo de prueba, y marcar dónde no coincide con `docs/`. Al cerrar cada tarea, antes de aprobar el PR. Hace una página interactiva solo si hay fórmulas o un concepto nuevo |

Los agentes no escriben reglas: las proponen en la sección "Aprendizajes" de su informe, y la sesión principal las registra con la skill `registrar-aprendizaje`.

`.claude/hooks/check-reglas.mjs` revisa automáticamente, al escribir un archivo: dominio puro, `steps` sin `adapters`, `server-only`, Lucide, `service_role`, límites de `app/` y versión de los prompts. También pide confirmación antes de editar una migración existente.

## Documentos de diseño

Léelos antes de proponer cambios. Si una decisión cambia, actualiza su documento **y** `docs/00-resumen-decisiones.md`.

| Archivo | Contenido |
| --- | --- |
| `docs/00-resumen-decisiones.md` | Todas las decisiones y su motivo; credenciales y variables por servicio |
| `docs/01-arquitectura.md` | Componentes, recorrido de un video, estados, adaptadores, escalabilidad |
| `docs/02-modelo-de-datos.md` | Tablas, enums, RLS por rol, funciones `rpc`, Realtime, índices |
| `docs/03-edicion-de-clips.md` | Edit Spec, JSON de decisiones, pipeline de clips |
| `docs/04-worker.md` | Cola, catálogo de pasos, grafo, leases, reintentos, costos |
| `docs/05-prompts.md` | Prompts, versionado, evals |
| `docs/06-arquitectura-del-codigo.md` | Carpetas, capas, dependencias, pruebas. **Manda sobre el árbol del 01** |
| `docs/07-plan-de-trabajo.md` | Sprints y tareas de la Fase 0 y la Fase 1 |
| `docs/progreso.md` | Registro de tareas cerradas, una línea por tarea |
| `materials/`, `design/references/` | Material real de la agencia · referencias visuales |

Las Fases 2, 3 y 4 **no están planificadas**: hay que escribirlas con el formato de `07` al cerrar la Fase 1.

## Reglas que no se negocian

**Claude decide, el worker ejecuta.** Claude recibe texto y devuelve JSON validado; nunca toca video. Postgres es la única fuente de verdad del estado, el video nunca pasa por Next.js y las API keys de IA viven solo en el worker.

**Límites**

- Código por módulo de dominio, hexagonal dentro de cada módulo. Los módulos se usan entre sí solo por su API pública: `index.ts` (web) o `api.py` (worker); nadie lee las tablas de otro módulo.
- El dominio es puro: nada de red, disco, base de datos ni `subprocess`. En el worker, `*/domain` no importa `psycopg`, `anthropic`, `assemblyai`, `boto3`, `mediapipe`, `playwright` ni `subprocess`.
- Los pasos hablan con el exterior por `ports/`; los `adapters/` los implementan y `bootstrap.py` los conecta. Nadie usa la respuesta cruda de un proveedor: solo tipos internos.
- `apps/web/src/modules/*/server/` empieza con `import 'server-only'`. `app/` solo compone páginas; `lib/` no importa `modules/`.

**Datos y permisos**

- El navegador **solo lee** (RLS + Realtime). Toda escritura pasa por una `rpc` que valida rol, asignación y estado; las Server Actions validan con zod y llaman a la `rpc`.
- Transiciones como `update … where status = <esperado>`.
- `service_role` nunca en el navegador; en la web solo para crear cuentas, verificando antes que quien llama es admin.
- Las versiones (perfil, reglas base, piezas) no se editan: cada cambio crea una nueva.
- Cada cambio de esquema es una migración nueva; nunca edites una aplicada. Cada cambio de RLS o `rpc` lleva su prueba pgTAP.

**Worker y prompts**

- Cada paso es idempotente, no escribe estados (los aplica el orquestador), valida con Pydantic y lanza `RetryableError`, `PermanentError`, `BudgetExceeded` o `NeedsConfirmation`. Claves de almacenamiento deterministas.
- Claude devuelve JSON validado con índices de palabras, nunca milisegundos ni píxeles, y no escribe HTML, Markdown ni schema: los arma el worker con plantillas.
- Prompts en `worker/prompts/*.md.j2` con encabezado de versión; cambiar un prompt = subir la `version` y correr `worker/evals`.
- Los modelos Pydantic son la fuente de los contratos: después de cambiarlos, `pnpm gen` y sube lo generado. Después de una migración, regenera `database.types.ts`.

**Convenciones**

- TypeScript `camelCase`, componentes `PascalCase`, archivos `kebab-case.ts`; Python y SQL `snake_case`; `rpc` como verbo + objeto (`approve_piece`); pasos como `modulo.accion` (`clip.compose`).
- Server Actions devuelven `{ ok: true, data }` o `{ ok: false, error }`; nunca lanzan al cliente.
- Configuración solo por variables de entorno, toda nueva a `.env.example`; nunca subas claves. Logs en JSON con `job_id`, `piece_id`, `step_id`.
- Todo módulo, clase y función lleva docstring completo (qué hace, argumentos, qué devuelve, errores, ejemplo si hay fórmula), escrito por el agente `documentador` con el estilo de `docs/06` §9.1.
- Textos de la interfaz en inglés, y también todo el código: nombres, comentarios, configuración, commits y logs. `docs/` sigue en español. Conventional Commits; ramas `feat/…` y `fix/…`; `main` protegida.

## Comandos

Scripts de la raíz, creados en el Sprint 1 (T1.2) y el Sprint 3.

| Comando | Hace |
| --- | --- |
| `pnpm dev:infra` | `supabase start` + MinIO en Docker |
| `pnpm dev:web` | Next.js en desarrollo |
| `pnpm dev:worker` | `docker compose up worker-io worker-cpu worker-maintenance` |
| `pnpm gen` | Tipos de Supabase + JSON Schema + tipos TS y zod |
| `pnpm test` / `pnpm test:db` | Vitest y pytest unitarios · pgTAP e integración del worker |
| `pnpm lint` | ESLint, Prettier, dependency-cruiser, Ruff, Pyright, import-linter |

Una sola prueba: `uv run python -m pytest tests/unit/test_timeline.py::test_nombre` en `worker/`, `pnpm vitest run archivo.test.ts -t "nombre"` en la web, `supabase test db` para pgTAP.

Antes de dar algo por terminado: `pnpm lint` y `pnpm test` en verde.
