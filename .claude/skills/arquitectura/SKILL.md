---
name: arquitectura
description: Mapa de la arquitectura del Content Engine: flujo de un video, estados de trabajo/pieza/paso, la cola en Postgres y sus dos colas io y cpu, que tablas son de cada modulo, el Edit Spec efectivo y los tipos de pieza como plugins. Usala antes de escribir o cambiar codigo del worker, del pipeline, de la base de datos o de las piezas, cuando haya que entender como encaja algo en el flujo, o cuando no sepas en que carpeta va lo que estas escribiendo.
---

# Arquitectura del Content Engine

Este es el mapa. El detalle completo esta en `docs/01` a `docs/06`; aqui esta lo suficiente para ubicarte y saber cual abrir.

## El principio del que sale todo

**Claude decide, el worker ejecuta.** Claude recibe texto (transcripcion, perfil, Edit Spec) y devuelve JSON validado; nunca toca archivos de video. El worker aplica ese JSON con FFmpeg, MediaPipe y Playwright.

Corolarios:

- **Postgres es la unica fuente de verdad del estado.** El worker no guarda nada en memoria; la UI se entera por Supabase Realtime.
- **El video nunca pasa por Next.js.** El navegador sube directo al almacenamiento con URLs firmadas (multipart reanudable, partes de 64 MB) y el worker lee desde ahi.
- **Las API keys de IA viven solo en el worker.** Next.js encola pasos; no llama a Claude ni a AssemblyAI. Por eso generar y regenerar usan el mismo codigo.
- **Cada trabajo congela su Edit Spec** en `jobs.effective_spec`: una pieza siempre se puede reproducir.
- **Cada paso es idempotente**, escribe con claves deterministas y se puede reintentar.

## Flujo de un video

```
probe -> extract_audio -> transcribe -> select_moments -> [una cadena por pieza] -> revision humana -> deliver
```

Los pasos forman un **grafo**, no una lista: cada paso tiene dependencias y el orquestador solo toma los que ya las tienen cumplidas. `select_moments` es el unico que **expande el grafo**: crea las filas de `pieces` segun el mix y sus cadenas de pasos, en la misma transaccion. El planificador (`pipeline/domain/planner.py`) es una funcion pura.

| Tipo de pieza | Cadena de pasos |
| --- | --- |
| `post`, `blog`, `newsletter` | `text.generate -> validate` |
| `quote` | `quote.generate -> quote.render -> validate` |
| `carousel` | `carousel.generate -> carousel.render -> validate` |
| `clip` | `clip.decide -> clip.extract -> clip.analyze -> clip.compose -> clip.verify -> validate` |

La validacion corre por pieza en cuanto esa pieza termina, asi el operador revisa texto mientras los clips renderizan. Una regeneracion es un paso nuevo del mismo tipo con el comentario como entrada extra: no reinicia el trabajo. En la Fase 1 solo existen las cadenas de texto.

Prioridades: 100 regeneraciones pedidas por una persona · 50 texto y validaciones · 10 render · 0 mantenimiento.

Catalogo completo de pasos con colas, intentos y tiempos maximos: `docs/04-worker.md` §4.1.

## Estados

| Que | Estados |
| --- | --- |
| `jobs.status` | `uploading -> queued -> processing -> in_review -> delivering -> delivered`; desvios: `needs_confirmation` (calidad dudosa), `paused_budget` (se paso el tope), `failed`, `cancelled` |
| `pieces.status` | `pending -> generating -> validating -> [in_video_review] -> ready -> approved`; desde `ready`: `regenerating -> validating -> ready` (version nueva). Una pieza `failed` no bloquea a las demas |
| `job_steps.status` | `waiting -> pending -> running -> succeeded \| failed \| cancelled` |

Si un paso falla, sus dependientes en `waiting` pasan a `cancelled`.

## La cola

Esta en Postgres (`job_steps`), no en Redis. Se toma con `select ... for update skip locked`, asi dos workers nunca agarran el mismo paso.

| Proceso | Que toma | Concurrencia |
| --- | --- | --- |
| `worker io` | Claude, AssemblyAI, descargas | un proceso asyncio, ~16 pasos a la vez, con limite por proveedor |
| `worker cpu` | FFmpeg, MediaPipe, Playwright, ZIP | un proceso por slot; slots = nucleos / 2 |
| `worker maintenance` | nada de la cola | recupera leases vencidos, retencion, trabajos trabados |

Dos colas para que un lote de clips no frene la regeneracion de un post.

**Despertar:** `LISTEN/NOTIFY` (un trigger hace `pg_notify('steps_' || queue, '')` cuando un paso queda `pending`), mas un temporizador para el `run_after` mas cercano y una consulta de respaldo cada 60 s por si se perdio un aviso. `LISTEN` necesita conexion directa o pooler en modo sesion.

**Lease y latido:** un paso `running` tiene `locked_until` (io: 2 min, latido cada 30 s; cpu: 5 min, latido cada 60 s). Si el worker muere, el lease vence y `maintenance` devuelve el paso a `pending`. El latido tambien detecta que se pidio cancelar.

## Modulos y sus tablas

Cada modulo es **dueño** de sus tablas: otro modulo no las lee directamente, pide los datos por la API publica (`api.py` / `index.ts`) o reacciona a sus eventos.

| Modulo | Tablas propias |
| --- | --- |
| `auth` | `profiles`, `client_assignments`, `app_settings` |
| `clients` | `clients`, `client_profile_versions`, `baseline_spec_versions`, `brand_assets`, `profile_examples`, `edit_spec_imports` |
| `ingest` | `transcripts` |
| `pipeline` | `jobs`, `job_steps` |
| `pieces` | `pieces`, `piece_versions` |
| `review` | `corrections`, `rule_proposals` |
| `delivery` | `packages`, `package_shares` |
| `usage` | `cost_events` |
| `integrations` | `outbox_events` |

Tablas, enums, politicas RLS y la lista completa de funciones `rpc`: `docs/02-modelo-de-datos.md`.

## Capas dentro de un modulo

| Capa | Web (TypeScript) | Worker (Python) |
| --- | --- | --- |
| Entrada | `app/` (paginas, Route Handlers) | `orchestrator/` |
| Casos de uso | `modules/<m>/server/` | `modules/<m>/steps/` |
| Dominio (puro) | `domain/` + `packages/schemas` | `modules/<m>/domain/` |
| Adaptadores | `lib/` | `adapters/` |

Los pasos hablan con el exterior por **puertos** (`ports/`: `llm.py`, `transcription.py`, `storage.py`, `media.py`, `repositories.py`); los adaptadores los implementan y `bootstrap.py` los conecta. Un paso recibe todo por `StepContext` (`job`, `piece`, `storage`, `llm`, `transcriber`, `budget`, `workdir`, `heartbeat()`, `log`).

Lo delicado del clip —timeline, camino de camara, subtitulos ASS, plan de render, argumentos de FFmpeg— es **dominio puro** y se prueba sin video. Solo *ejecutar* FFmpeg es un adaptador.

## El Edit Spec efectivo

```
reglas base de la agencia (baseline_spec_versions)  +  Edit Spec del cliente
                      -> spec efectivo, congelado en jobs.effective_spec
                      -> lo usan Claude, el render y la revision automatica
```

Combinacion por area:

- `params`: gana el cliente **campo por campo**. Si el area del cliente esta `to_confirm`, se usan los `params` base.
- `rules` (texto): se concatenan, primero las base, salvo las que el cliente marque en `overrides`.
- `never_do` y `qc_extras`: union de base y cliente.

Son 15 areas (`format_length`, `hook`, `pacing`, `camera_framing`, `captions`, `fonts_colors`, `logo`, `broll_assets`, `music_sound`, `graphics_transitions`, `tone`, `cta_end_screen`, `templates`, `export`, `delivery`) mas `never_do`. Cada regla de `never_do` dice como se verifica: `auto`, `llm` o `manual`. Detalle: `docs/03-edicion-de-clips.md` §2.

## Tipos de pieza como plugins

Cada tipo (`clip`, `carousel`, `post`, `blog`, `newsletter`, `quote`) es un paquete en `worker/src/content_engine/piece_types/` registrado en `registry.py` con contrato fijo: `key`, esquema del contenido (Pydantic), prompt, generador, renderizador, validaciones, cola que usa y componente de vista previa en la UI.

El orquestador arma el grafo leyendo el mix y el registro: no tiene una lista fija de tipos. **Agregar "hilo de X" o "miniatura de YouTube" es agregar una carpeta, no modificar el pipeline.** Receta de 7 pasos: `docs/06-arquitectura-del-codigo.md` §12.

## Adaptadores (todo proveedor es intercambiable)

`TranscriptionProvider` (AssemblyAI) · `LLMProvider` (Claude) · `ObjectStorage` (S3: MinIO o R2) · `SourceFetcher` (P1) · `DeliveryTarget` (ZIP + link) · `Notifier` (Fase 3) · `StockFootage` (P1).

Nadie usa la respuesta cruda de un proveedor: solo tipos internos (`Transcript`, `Word`, `Moment`, `EditDecision`). Los nombres de modelo no van en el codigo: `model_role` (`generate`, `validate`) se resuelve desde `CLAUDE_MODEL_GENERATE` / `CLAUDE_MODEL_VALIDATE`.

## Que esta fuera del MVP

Multiinquilino (`org_id`, membresias, registro publico, cobro) · graficos animados explicativos · layout con graficos arriba · varias camaras o pantalla dividida · formatos distintos de 9:16 · Google Drive · B-roll e imagenes del cliente (P1) · links de YouTube/Zoom/Loom (P1) · audio y documentos como entrada (Fase 3) · ClickUp y Slack (Fase 3).
