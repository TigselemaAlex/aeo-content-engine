# Content Engine: resumen de decisiones

**Fecha:** 12 de noviembre de 2026 · **Autor:** Alex Tigselema

Resumen de lo decidido al revisar el documento de requerimientos del Content Engine de AEO.co. Sirve como punto de partida para generar los documentos de desarrollo. Reemplaza en lo técnico a la propuesta anterior, que todavía incluía Opus Clip.

## Contexto del proyecto

Aplicación web interna de AEO.co: el operador sube el video largo de un cliente y la herramienta genera 20 piezas aplicando el Edit Spec de cada cliente:

- 6 clips verticales
- 4 carruseles
- 6 posts de texto
- 1 blog AEO
- 1 newsletter
- 2 gráficos de cita

El operador revisa, corrige con comentarios o regenera, y envía el paquete. Hay tres roles: operador, administrador y revisor de video (temporal).

## Decisiones tomadas

| Tema | Decisión | Motivo |
| --- | --- | --- |
| APIs de IA | Claude para decidir y escribir; AssemblyAI para transcribir; todo lo demás con librerías open source | La agencia entrega solo esas dos API keys |
| Edición de clips | Pipeline propio en Python: FFmpeg para corte, subtítulos, logo, zooms, música, intro y outro; MediaPipe para el reencuadre al hablante | Control total del Edit Spec sin depender de servicios externos de video |
| Patrón de trabajo | Claude decide y el worker ejecuta: Claude devuelve un JSON con las decisiones de edición (rango, hook, zooms, estilo) y el worker lo aplica con FFmpeg | Predecible y fácil de probar; Claude no procesa video |
| Selección de momentos | Claude elige los momentos con el perfil del cliente a partir de la transcripción | La estrategia queda en manos de la herramienta |
| Transcripción | AssemblyAI con tiempos por palabra e identificación de hablantes | Es la base de todo: Claude lee el texto y los tiempos permiten cortar, subtitular, quitar muletillas y verificar citas |
| Muletillas y glosario (17 nov 2026) | AssemblyAI con su modelo por defecto, `disfluencies` y el glosario por `keyterms_prompt`. AssemblyAI no marca las muletillas: el worker las detecta con su propia lista (`is_disfluency` en cada palabra; "uh-huh" y "mhm" no cuentan porque suelen ser respuestas). La `confidence` de cada palabra queda guardada | Comprobado en la T1.4: con `disfluencies` las muletillas solo dejan de borrarse. Las palabras mal transcritas salen con confianza baja ("AIO" en vez de "AEO", 0,33) |
| Transcripción como núcleo compartido (18 nov 2026) | `Word` y `Transcript` viven en `worker/src/content_engine/shared/transcript.py`, no en `modules/ingest/domain`. La detección de muletillas sigue en `ingest`. A `shared` solo entra lo que usan varios módulos, es dato puro y cambia poco (`06` §5.2) | Un `domain` no puede importar el de otro módulo, y el timeline del clip (T1.5), los posts y las citas trabajan sobre las mismas palabras indexadas; copiar el tipo en cada módulo duplicaría campos y conversiones |
| Pausas largas en el timeline (18 nov 2026) | Una pausa mayor a `pause_max_ms` parte el tramo en dos, como una muletilla; el silencio que queda lo forman los márgenes de corte (≈ 120 ms después + 60 ms antes), sin una duración de pausa propia de ~150 ms (`03` §5.1) | Un solo mecanismo para todos los cortes; con dos reglas separadas el margen y la pausa se sumaban (≈ 330 ms). La diferencia entre 150 y 180 ms casi no se oye |
| J cuts en el timeline (18 nov 2026) | Se aplica el valor del medio de `j_cut_frames` (4 fotogramas ≈ 133 ms a 30 fps) en todas las uniones. `Timeline.cuts` sigue siendo el audio y se agrega `video_cuts`: la imagen del corte anterior se alarga y la del siguiente empieza ese tiempo después, y la imagen total dura lo mismo que el audio (`03` §5.1) | Un valor fijo mantiene el paso idempotente sin reglas de variación; dejar el audio intacto conserva el mapa de tiempos de los subtítulos, y calcularlo en el timeline lo deja en código puro y fácil de probar en vez de en la extracción con FFmpeg |
| Extracción del intermedio (19 nov 2026) | Una entrada de FFmpeg por rango, con búsqueda de entrada: dos por tramo (imagen de `video_cuts`, audio de `cuts`) unidas con `concat` y fijadas a 30 fps. H.264 CRF 16 preset `veryfast`, AAC 48 kHz 192 kbps. Márgenes de corte sin cambios (60 ms antes, 120 ms después): el tramo de prueba de 51 s (palabras 185–298) se oye bien (`03` §5.2) | Saltar al punto exacto es rápido aunque el original dure 1 hora, y respeta los rangos distintos de imagen y audio de los J cuts. El intermedio es temporal: importa más la velocidad que el tamaño. Los falsos inicios ("pick a few source- pick…") no son tarea del timeline: los evita el rango o los `extra_cuts` que decide Claude (Sprint 2) |
| Base de datos | Supabase (Postgres, Auth, Storage, Realtime para el estado de cada trabajo) | Funciona en local con la CLI y luego en la nube sin cambiar código |
| Login | Correo y contraseña con Supabase Auth, sin Google; el registro público queda desactivado y el administrador crea las cuentas | Más simple para el MVP y el acceso sigue limitado al equipo de AEO.co (RNF-04) |
| Videos y archivos | MinIO en local y Cloudflare R2 en despliegue para todos los archivos, con subida reanudable multipart directa desde el navegador. Supabase Storage no se usa | El mismo código de subida funciona en ambos entornos; pasar a R2 es solo configuración |
| Entrega del paquete | ZIP descargable + link compartible de solo lectura con vencimiento (ruta `/p/{token}` de la app). Sin Google Drive en el MVP | No depender de cuentas externas; el adaptador de entrega permite conectar Drive u otro destino después |
| Estilo de arquitectura | Monolito modular con worker asíncrono y cola en Postgres; módulos con límites explícitos (cada uno dueño de sus tablas); capas con puertos y adaptadores; dos colas (`io` y `cpu`) | Suficiente para 10 veces la carga esperada agregando máquinas; microservicios no aportan a esta escala y un módulo se puede separar después sin reescribir |
| SaaS / multiinquilino | Fuera del MVP: una sola organización (AEO.co), sin `org_id` ni membresías. Si se decide vender, se hace una migración a base compartida con `org_id` + RLS, acordada con AEO.co | Es un MVP para una agencia; no se construye lo que no está en el alcance |
| Backend | Sin framework backend aparte (NestJS o FastAPI): Supabase cubre login, permisos y tiempo real; la API delgada vive en Route Handlers de Next.js; lo pesado, en el worker. Se extrae un backend solo si la API la consumen otros sistemas o crece mucho la lógica | Evitar un tercer despliegue sin beneficio |
| Escalar en funcionalidades | Tipos de pieza como plugins con contrato fijo; eventos de dominio con outbox (ClickUp, Slack y futuros webhooks se suscriben); funciones activables por cliente | Agregar un formato nuevo o una integración no toca el núcleo (RNF-10) |
| Edit Spec | Reglas base de la agencia (globales, versionadas) + Edit Spec del cliente que las sobrescribe; 15 áreas de la plantilla de la agencia, cada una con parámetros, reglas en texto y estado confirmado/por confirmar. Cada trabajo congela el spec efectivo | Es el proceso que la agencia ya usa (`materials/ref_client-video-editing-rules.md`) |
| Gráficos animados explicativos | Fuera de alcance (diagramas paso a paso, búsquedas escritas, tarjetas, layout gráficos arriba). Los agrega el revisor de video si el cliente los pide | RF-10 no los incluye |
| Duración de clips | 30 a 60 s por defecto (regla base de la agencia); el cliente puede extender hasta 90 s | Requerimiento 30–90 s + regla base "under 60 s" |
| Hook | Texto en pantalla con palabra clave resaltada + opción de abrir con una frase fuerte de más adelante del mismo momento | Regla base: abrir con la pregunta o la frase más sorprendente |
| Origen de comentarios | Cada corrección indica si es del cliente (con sus palabras) o interna | Change log de la agencia y métrica de comentarios repetidos del cliente |
| Reencuadre | Prioridad: una persona a cámara grabada en horizontal (caso Guidepost). Dos personas en el mismo plano se contemplan; varias cámaras no entran en el MVP | Tipo de video que llega hoy |
| Arquitectura del código | Mezcla: módulos por dominio (monolito modular) y, dentro de cada módulo, capas con puertos y adaptadores. Se detalla en el documento 6 | Definido en `01-arquitectura.md` §2.1 |
| Prompts | Prompts en inglés como archivos versionados en `worker/prompts/`; salida siempre JSON con esquema; orden fijo para aprovechar la caché; Claude no escribe HTML, Markdown ni schema (los arma el worker con plantillas) | RNF-10 y salidas sin errores de formato |
| Formato de blog y newsletter | Supuesto: el del requerimiento (TL;DR, subtítulos-pregunta con respuesta directa, FAQ, FAQPage, bio; newsletter con 3 asuntos, preheader, cuerpo y CTA) hasta que la agencia entregue el suyo | El formato real no está en `materials/` |
| Autor | Campo `voice.author` en el perfil (nombre, cargo, bio, foto) para blog, newsletter y citas | Consistencia entre piezas |
| Memoria en prompts | Reglas aceptadas (en el spec) + últimas 10 correcciones del mismo tipo de pieza + hasta 3 ejemplos marcados por el admin | RF-17 |
| No inventar datos | Cada pieza devuelve sus afirmaciones con el rango de la transcripción; el worker verifica que cada cifra y cita exista en la fuente; Haiku confirma en la Fase 3 | Regla del requerimiento para todas las piezas |
| Código | Monorepo con pnpm workspaces + uv; web con Tailwind + shadcn/ui, Server Components + TanStack Query actualizado por Realtime, Server Actions → `rpc`; contratos desde Pydantic a JSON Schema, TS y zod; reglas de dependencia verificadas en CI (dependency-cruiser, import-linter) | Detalle en `06-arquitectura-del-codigo.md` |
| Plan de trabajo | Sprints de 2 semanas (6 para Fase 0 y Fase 1), tareas con subtareas paso a paso en lenguaje sencillo; Alex escribe el código con guía tipo tutorial. Se pasa a ClickUp cuando el conector funcione | Aprender y poder repetir las tareas sin ayuda; sin presión de fechas |
| Acceso a datos | Sin ORM. Next.js usa supabase-js con tipos generados (`supabase gen types`): lecturas con RLS y escrituras con funciones `rpc`. El worker usa psycopg con SQL y modelos Pydantic. Esquema, RLS y funciones en migraciones SQL de la CLI de Supabase | Un ORM se conecta sin la identidad del usuario y se salta RLS; además chocaría con las migraciones de Supabase |
| Revisor de video | Se le asignan clientes como al operador; ve solo clips de sus clientes con la etapa activa | Mismo modelo de permisos para ambos roles |
| Tope de costo (RNF-05) | Máximo en USD por video, configurable por cliente con un valor por defecto global; si se supera, el trabajo se pausa | Control por video, que es la unidad que procesa la herramienta |
| Ediciones manuales | Cuentan como corrección: se guardan en la memoria y la pieza no cuenta como "aprobada sin cambios" | La métrica refleja el trabajo real del operador |
| Ejemplos del perfil | Los marca el admin desde el historial; también puede subir ejemplos externos | Control de calidad de lo que Claude imita |
| Worker en local | Contenedor Docker con Docker Desktop (Windows), la misma imagen que en despliegue | Evita diferencias entre la máquina del desarrollador y el servidor |
| Repositorio | GitHub público personal (decidido el 13 nov 2026; permite proteger `main` sin plan de pago); se transfiere a la organización de AEO.co en la Fase 4 | Arrancar sin depender de la agencia y cumplir RNF-09 al final |
| Instrucciones para Claude Code | `CLAUDE.md` y `.claude/` (skills, agentes, hooks) se versionan y viajan con el repo; la forma de trabajo personal vive en `.claude/rules/forma-de-trabajo.md`, cargada por `CLAUDE.local.md`, y queda fuera de git | Las reglas del proyecto le sirven a quien lo herede; las preferencias de trato no, y el repo pasa a la agencia (RNF-09) |
| Audio y documentos como entrada | Fase 3 | Reutilizan el pipeline de texto sin trabajo de video |
| App web | Next.js + React + TypeScript | Stack sugerido y fuerte del desarrollador |
| Idioma del código | Inglés en nombres, comentarios, configuración, commits y logs; `docs/` en español | El repo pasa a la agencia (RNF-09), cuyo equipo trabaja en inglés |
| Versión de Node.js | Node.js 26 (LTS) | La 22 está por terminar su soporte; la 26 ya es LTS y es la instalada |
| Tipos en Python | Pyright en modo `strict` en el worker (`src` y `tests`) | Detecta errores de tipos desde el principio, cuando todavía hay poco código que ajustar |
| Archivo `.env` | Uno solo, en la raíz del monorepo; el worker lo lee como `../.env` (un `worker/.env` opcional lo sobrescribe) | Las claves se escriben una vez para la web y el worker |
| IA de texto | Claude API: Sonnet 5.5 para generar, Haiku 5.5 para validar, con caché de prompts. El identificador exacto de cada modelo va en variables de entorno (`CLAUDE_MODEL_GENERATE`, `CLAUDE_MODEL_VALIDATE`) | Cada modelo en la tarea que le corresponde; cambiar de versión no requiere tocar código |
| Carruseles y gráficos | Plantillas HTML por cliente renderizadas a PNG con Playwright | Se editan como HTML, sin herramientas de diseño |
| B-roll | Material propio del cliente y Pexels como respaldo, activable por cliente; prioridad P1 | Se agrega después de tener los clips básicos funcionando |
| Proveedores intercambiables | Cada servicio (transcripción, IA, clips, almacenamiento) detrás de un adaptador propio | Cumple RNF-08 y permite cambiar de proveedor sin reescribir la app |
| Fases | Fase 0 de 1 semana (prototipo de clip propio con FFmpeg y MediaPipe), Fase 1 de 4 a 5, Fase 2 de 5 a 7, Fase 3 de 3 a 4, Fase 4 de 2 más 4 de observación | Total de 15 a 19 semanas de desarrollo; la Fase 2 es la de mayor riesgo |
| Criterios de aprobación | Cada fase se aprueba por sus requisitos funcionando con un video real; las métricas de uso quedan como meta conjunta | Las métricas dependen también de la operación de la agencia |
| Ajustes de alcance | Links de YouTube, Zoom, Loom y Google Drive pasan a P1 (P0 es solo subida directa); RF-16 entrega ZIP + link compartible en lugar de copiar a Drive; el login con Google (RF-01) pasa a correo y contraseña; "aprende de cada corrección" significa guardar correcciones, usarlas como ejemplos y proponer reglas; el tiempo de 60 minutos cuenta desde que termina la subida; "0 comentarios repetidos" pasa a "una regla no reaparece más de 1 vez por cliente" | Requisitos verificables y realistas |
| Demo | Un video de 15 a 20 minutos, las piezas de texto y 2 o 3 clips con subtítulos, logo y reencuadre | Mostrar el flujo completo funcionando |
| Material de prueba (16 nov 2026) | Tres niveles: **grabación propia** de 2–3 min (Alex, en inglés, horizontal, una persona a cámara) para los Sprints 1 y 2, y un recorte suyo de 20 s como video de `worker/tests/fixtures/`; **video largo de prueba** de 1 h o más (inglés, una persona a cámara, licencia CC BY) desde el Sprint 4 para medir tiempos, costos y la subida en partes; **video real del cliente** para la prueba final (T6.5). Ningún video de terceros se sube al repo. El Edit Spec de Guidepost se sigue usando como spec de prueba | La agencia no puede compartir videos de clientes por ahora. Los videos reales son crudos de más de 1 h; el límite de 2 h del probe se mantiene |

## Arquitectura (resumen)

Claude es el cerebro y el worker son las manos. Claude nunca toca el video: lee la transcripción y el Edit Spec, y devuelve decisiones en JSON. Detalle en `01-arquitectura.md`.

## MVP en local

- **Web:** Next.js en modo desarrollo.
- **Supabase:** con la CLI (`supabase start`): Postgres, Auth, Storage y Realtime en Docker.
- **Almacenamiento de archivos:** MinIO en Docker.
- **Worker:** contenedor Docker con Python que toma pasos de una cola en Postgres.
- **Dependencias del sistema:** dentro de la imagen del worker (FFmpeg, MediaPipe, Playwright con Chromium, tipografías).
- **Material de prueba:** Edit Spec real de Guidepost en `materials/`; videos propios y Creative Commons hasta tener uno real del cliente (ver "Material de prueba" en las decisiones).

## API keys y credenciales necesarias

| Servicio | Para qué | Variables | Cuándo |
| --- | --- | --- | --- |
| Anthropic (Claude) | Selección de momentos, piezas de texto y validación | `ANTHROPIC_API_KEY` | MVP local |
| AssemblyAI | Transcripción con tiempos por palabra e identificación de hablantes | `ASSEMBLYAI_API_KEY` | MVP local |
| Supabase | Base de datos, login, Storage y Realtime | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | En local las genera la CLI; en despliegue, las del proyecto en la nube |
| MinIO | Archivos en local | `S3_ENDPOINT`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` | MVP local |
| Google Drive API | Fuera del MVP; solo si se retoma la entrega o los links de Drive (P1) | `GOOGLE_SERVICE_ACCOUNT_JSON` | Por definir |
| Pexels | B-roll de respaldo | `PEXELS_API_KEY` | P1 |
| ClickUp | Crear la tarea cuando el paquete está listo (RF-18) | `CLICKUP_API_TOKEN` | Fase 3 |
| Slack | Avisar cuando el paquete está listo (RF-18) | `SLACK_BOT_TOKEN` | Fase 3 |
| Cloudflare R2 | Almacenamiento de videos en despliegue | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | Despliegue |
| Sentry | Monitoreo de errores | `SENTRY_DSN` | Despliegue |

## Despliegue (después del MVP)

- **Web:** Next.js en Vercel Pro o Netlify. El plan gratis de Vercel no permite uso comercial.
- **Supabase:** proyecto en la nube; migración con las migraciones de la CLI.
- **Videos:** Cloudflare R2, subida directa con URL firmada.
- **Worker en Python:** Trigger.dev con máquinas grandes o un VPS propio con Docker; comparar con datos reales.
- **Lectura de video:** FFmpeg lee solo los segmentos necesarios desde R2 con URL firmada.
- **Propiedad:** cuentas a nombre de la agencia y código en un repositorio de GitHub de AEO.co (RNF-09).

## Puntos técnicos a validar en la Fase 0

- **Reencuadre con varias personas:** combinar MediaPipe con la identificación de hablantes de AssemblyAI.
- **Calidad de subtítulos:** resaltado palabra por palabra sincronizado con los tiempos de AssemblyAI.

## Pendientes de decidir

- **Videos en HDR:** los teléfonos recientes graban en HDR por defecto (`color_transfer` `arib-std-b67` o `smpte2084`). El intermedio se guarda en `yuv420p` sin ajuste de tono, así que un video HDR sale lavado y sin contraste, sin dar error. Opciones: convertirlo a SDR con *tone mapping* o pasar a `needs_confirmation` para que el operador decida. Se decide en el paso `probe` (Sprint 4); mientras tanto, las grabaciones de prueba se hacen con el HDR apagado.

## Documentos de desarrollo

1. Arquitectura del sistema con el flujo completo de un video — `01-arquitectura.md` ✅
2. Modelo de datos en Supabase, con permisos por rol — `02-modelo-de-datos.md` ✅
3. Formato del JSON de decisiones de edición y el pipeline de clips con FFmpeg y MediaPipe — `03-edicion-de-clips.md` ✅
4. Diseño del worker en Python: pasos, cola, reintentos y estados — `04-worker.md` ✅
5. Prompts de Claude: selección de momentos, generación de piezas y validación — `05-prompts.md` ✅
6. Arquitectura del código: estructura de carpetas, capas, reglas de dependencia, convenciones y pruebas por capa — `06-arquitectura-del-codigo.md` ✅
7. Plan de trabajo de la Fase 0 y la Fase 1 con tareas concretas — `07-plan-de-trabajo.md` ✅
