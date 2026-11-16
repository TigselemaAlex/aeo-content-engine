# 07 · Plan de trabajo: Fase 0 y Fase 1

**Proyecto:** Content Engine (AEO.co) · **Fecha:** 13 de noviembre de 2026 · **Autor:** Alex Tigselema

Plan para construir la Fase 0 (prototipo de clips) y la Fase 1 (base de la app y piezas de texto). Está escrito como un tutorial: cada tarea dice qué vas a construir, qué vas a aprender y los pasos en orden. La idea es que tú escribas el código y que más adelante puedas repetir estas tareas sin ayuda.

Está listo para pasarlo a ClickUp: cada **sprint** es una lista, cada **tarea** es una tarea y cada **paso** es una subtarea.

---

## Cómo trabajamos

1. **Eliges una tarea** (por ejemplo, "T1.3") y me dices "vamos con T1.3".
2. **Te explico qué vamos a hacer** con palabras simples y, si hace falta, con un ejemplo.
3. **Tú escribes el código.** Te digo qué escribir y por qué; no te doy todo resuelto, salvo que me lo pidas o que sea algo de configuración sin nada que aprender.
4. **Lo pruebas.** Cada paso dice cómo saber que funcionó.
5. **Lo reviso contigo** si quieres: me muestras el código y te digo qué mejorar.
6. **Marcas la subtarea como hecha.**

Reglas para las explicaciones:

- Sin términos complicados ni siglas sin explicar. Si aparece una palabra técnica, va en el glosario o se explica ahí mismo.
- Ejemplos solo cuando ayudan; lo simple se dice simple.
- Si algo no queda claro, se explica de otra forma antes de seguir.

---

## Glosario

| Palabra | Qué significa |
| --- | --- |
| **Repositorio (repo)** | La carpeta del proyecto con el historial de todos los cambios. Se maneja con `git`. |
| **Monorepo** | Un solo repositorio con varias partes adentro (la web, el worker). |
| **Terminal** | La ventana donde escribes comandos. |
| **Docker / contenedor** | Una "caja" que trae un programa con todo lo que necesita, para que funcione igual en cualquier computadora. |
| **Base de datos, tabla, fila, columna** | Donde se guardan los datos. Una tabla es como una hoja de Excel: cada fila es un registro y cada columna un dato. |
| **SQL** | El lenguaje para pedirle cosas a la base de datos (`select * from clients`). |
| **Migración** | Un archivo SQL que crea o cambia tablas. Se guarda en el repo para poder reconstruir la base igual en cualquier lado. |
| **Supabase** | El servicio que nos da la base de datos (Postgres), el login y los avisos en tiempo real. Lo corremos en tu computadora. |
| **Permisos por fila** | Reglas dentro de la base que deciden qué filas puede ver cada usuario. En Supabase se llaman RLS. |
| **Función de base de datos** | Una función escrita en SQL que vive en la base. La web la llama para guardar cambios siguiendo reglas (en Supabase se llama con `rpc`). |
| **JSON** | Un formato de texto para datos: `{ "nombre": "Kyle", "edad": 40 }`. |
| **API** | La "puerta" para que un programa le pida cosas a otro. Claude y AssemblyAI tienen una. |
| **API key** | La contraseña para usar una API. Nunca se sube al repo. |
| **Variable de entorno** | Un valor de configuración (por ejemplo, una API key) que vive en un archivo `.env`, fuera del código. |
| **Worker** | El programa en Python que trabaja en segundo plano: transcribe, llama a Claude, edita video. |
| **Cola / paso** | La cola es la lista de trabajos pendientes. Cada trabajo pequeño (transcribir, generar un post) es un paso. |
| **Prueba (test)** | Código que revisa que otro código hace lo que debe. |
| **Componente** | Una pieza de la pantalla: un botón, una tarjeta, un formulario. |
| **FFmpeg** | Programa de línea de comandos para cortar, unir y transformar video y audio. |
| **MediaPipe** | Librería de Google que detecta caras en imágenes. |
| **Transcripción con tiempos** | El texto del video donde cada palabra trae el momento exacto en que se dijo. |
| **9:16** | Formato vertical (como TikTok o Reels): 1080 de ancho por 1920 de alto. |
| **Sprint** | Un bloque de 2 semanas con un objetivo que se puede mostrar al final. |

---

## Resumen de sprints

Con más de 20 horas por semana. Los estimados incluyen tiempo para repasar y aprender; no son fechas límite. Si un sprint se pasa de 2 semanas, no pasa nada: lo que importa es cumplir su objetivo.

| Sprint | Objetivo | Fase | Estimado |
| --- | --- | --- | --- |
| **S1** | Preparar todo y dar los primeros pasos con video y transcripción | 0 | ~45 h |
| **S2** | Prototipo de clip: de un video horizontal a un clip vertical con subtítulos | 0 | ~55 h |
| **S3** | Base de datos, login y clientes | 1 | ~60 h |
| **S4** | Subir un video y procesarlo con la cola del worker | 1 | ~50 h |
| **S5** | Generar las piezas de texto y la pantalla de revisión | 1 | ~50 h |
| **S6** | Entregar el paquete, historial y prueba con un video real | 1 | ~40 h |

La Fase 1 queda en 4 sprints (8 semanas) en lugar de las 4 a 5 semanas del resumen de decisiones, porque incluye repaso. Si avanzas más rápido, se adelanta.

## Etiquetas

`preparacion` · `video` · `ia` · `base-de-datos` · `web` · `worker` · `pruebas` · `documentacion`

## Formato de cada tarea

- **Qué vas a construir** y **qué vas a aprender**.
- **Lee antes:** la sección del documento que explica el diseño.
- **Pasos** (subtareas), cada uno con su forma de comprobar que funcionó (✔).
- **Terminaste cuando:** la condición para cerrar la tarea.

---

# Sprint 1 · Preparar todo y primeros pasos con video

**Objetivo:** tener el proyecto armado en tu computadora, transcribir un video y cortar un tramo con FFmpeg desde Python.
**Al final muestras:** un script que transcribe tu grabación de prueba y otro que corta un tramo exacto por palabras.

> **Material de prueba.** La agencia no puede compartir videos de clientes por ahora. Usamos tres niveles (`00-resumen-decisiones.md`, "Material de prueba"): tu **grabación propia** de 2–3 min para los Sprints 1 y 2, un **video largo de prueba** de 1 h o más con licencia CC BY desde el Sprint 4, y un **video real del cliente** para la prueba final (T6.5). El Edit Spec de Guidepost se sigue usando como spec de prueba.

### T1.1 · Instalar las herramientas
`preparacion` · ~4 h

**Qué vas a construir:** tu computadora lista para el proyecto.
**Qué vas a aprender:** qué hace cada herramienta y cómo comprobar que está instalada.

1. Instalar **Git** y configurar tu nombre y correo. ✔ `git --version` responde.
2. Instalar **Docker Desktop** con WSL2 activado (en Windows, Docker usa un Linux por dentro). ✔ `docker run hello-world` muestra un saludo.
3. Instalar **Node.js 26** (LTS) y **pnpm** (instalador de paquetes de JavaScript). ✔ `node -v` y `pnpm -v` responden.
4. Instalar **uv** (instalador de paquetes y versiones de Python). ✔ `uv --version` responde.
5. Instalar la **CLI de Supabase** (el programa de terminal de Supabase). ✔ `supabase --version` responde.
6. Instalar **FFmpeg**. ✔ `ffmpeg -version` responde.
7. Instalar en VS Code las extensiones de Python, ESLint, Prettier y Tailwind.

**Terminaste cuando:** los seis comandos de comprobación responden sin error.

### T1.2 · Crear el repositorio y su estructura
`preparacion` · ~4 h
**Lee antes:** `06-arquitectura-del-codigo.md` §3.

**Qué vas a construir:** el monorepo vacío con sus carpetas.
**Qué vas a aprender:** cómo se organiza un monorepo y para qué sirve cada archivo de la raíz.

1. Inicializar git en `C:\Projectos\aeo-content-engine` (ya tiene `docs/`, `materials/`, `design/` y `.claude/`). ✔ `git status` muestra los archivos.
2. Crear `.gitignore`: lista de lo que git no debe guardar (`.env`, `node_modules`, videos y lo personal que no debe pasar al repositorio de la agencia: `CLAUDE.local.md` y `.claude/rules/`). ✔ Un `.env` de prueba no aparece en `git status`.
3. Crear las carpetas `apps/`, `worker/`, `packages/`, `supabase/`, `templates/`.
4. Crear `pnpm-workspace.yaml` (le dice a pnpm dónde están las partes) y el `package.json` de la raíz.
5. Crear `.env.example` con los nombres de las variables (sin valores reales) y tu `.env` con las claves de AssemblyAI y Claude.
6. Crear el repo público en tu GitHub, subir el primer commit y proteger la rama `main`. ✔ Se ve en GitHub sin el `.env`.

**Terminaste cuando:** el repo está en GitHub con la estructura y sin claves.

### T1.3 · Repaso de Python con el proyecto del worker
`worker` · `preparacion` · ~6 h

**Qué vas a construir:** el proyecto Python del worker con un comando que funciona.
**Qué vas a aprender:** uv, entornos de Python, tipos, Pydantic y cómo leer variables de entorno.

1. `uv init` dentro de `worker/` y configurar `src/content_engine/`. ✔ `uv run python -c "import content_engine"` no da error.
2. Agregar Ruff (revisa y formatea el código) y Pyright (revisa los tipos). ✔ `uv run ruff check` y `uv run pyright` pasan.
3. Crear `config.py` con **pydantic-settings**: una clase que lee el `.env` y avisa si falta una clave. *Ejemplo: si falta `ASSEMBLYAI_API_KEY`, el programa se detiene con un mensaje claro.* ✔ Funciona con y sin la clave.
4. Crear `main.py` con un comando `hello` usando **Typer** (librería para comandos de terminal). ✔ `uv run content-engine hello` imprime algo.
5. Agregar pytest y escribir tu primera prueba. ✔ `uv run pytest` pasa.

**Terminaste cuando:** `ruff`, `pyright` y `pytest` pasan y el comando responde.

### T1.4 · Transcribir tu grabación de prueba
`ia` · `worker` · ~8 h
**Lee antes:** `03-edicion-de-clips.md` §3.

**Qué vas a construir:** un comando que extrae el audio de un video, lo envía a AssemblyAI y guarda la transcripción con tiempos por palabra.
**Qué vas a aprender:** usar FFmpeg desde Python, llamar a una API externa y modelar datos con Pydantic.

1. Grabarte 2–3 min en inglés, en horizontal, hablando a cámara, y copiar el video a `worker/tests/fixtures/` (el `.gitignore` ya evita que se suban los videos).
2. Extraer el audio con FFmpeg desde Python usando `subprocess`: mono, 16 kHz, `.m4a`. ✔ El archivo se escucha bien y pesa mucho menos que el video.
3. Instalar el SDK de AssemblyAI y pedir la transcripción con **muletillas** ("um", "uh") e **identificación de hablantes**, y con un glosario (`AEO`, `ChatGPT`) como vocabulario. ✔ Llega el texto.
4. Crear los modelos Pydantic `Word` (texto, inicio en ms, fin en ms, hablante, confianza, si es muletilla) y `Transcript`.
5. Convertir la respuesta de AssemblyAI a tu `Transcript` y guardarla como JSON. *Este paso de "traducir" la respuesta del proveedor a un formato propio es lo que permite cambiar de proveedor sin romper el resto.* ✔ El JSON tiene índice, texto y tiempos por palabra.
6. Imprimir un resumen: número de palabras, duración, cuántas muletillas.

**Terminaste cuando:** tienes `transcript.json` de tu grabación y entiendes cada campo.

### T1.5 · Timeline: de palabras a cortes (lógica pura)
`video` · `pruebas` · ~12 h
**Lee antes:** `03-edicion-de-clips.md` §5.1.

**Qué vas a construir:** la función que recibe palabras y decide qué tramos del video conservar.
**Qué vas a aprender:** escribir lógica sin depender de archivos ni internet, y probarla con pruebas automáticas.

1. Crear `piece_types/clip/domain/timeline.py` con los modelos `Segment` (desde la palabra X hasta la Y) y `Timeline` (lista de cortes + duración final).
2. Función que convierte rangos de palabras en tiempos usando la transcripción. ✔ Prueba: palabras 10–20 → el inicio de la palabra 10 y el fin de la 20.
3. Quitar muletillas. ✔ Prueba con una lista inventada que tenga "um".
4. Recortar pausas largas (más de 500 ms) a unos 150 ms. ✔ Prueba con un hueco de 2 s entre dos palabras.
5. Agregar margen a cada corte (60 ms antes, 120 ms después) sin pisar la palabra vecina. ✔ Prueba con palabras muy juntas.
6. Calcular el **mapa de tiempos**: dónde cae cada palabra en el clip final. *Ejemplo: si quitas 1 s de pausa, todo lo que viene después se mueve 1 s antes.* ✔ Prueba con una pausa quitada.
7. Agregar los **J cuts**: el audio del tramo siguiente empieza unos fotogramas antes que la imagen.

**Terminaste cuando:** todas las pruebas pasan y puedes explicar el mapa de tiempos con un ejemplo.

### T1.6 · Cortar el video según el timeline
`video` · ~8 h
**Lee antes:** `03-edicion-de-clips.md` §5.2.

**Qué vas a construir:** un comando que toma la transcripción, un rango de palabras y el video, y genera el tramo cortado y unido.
**Qué vas a aprender:** cómo FFmpeg corta con precisión y une tramos.

1. Función pura que arma la lista de argumentos de FFmpeg a partir del `Timeline`. ✔ Prueba: compara la lista generada con la esperada.
2. Ejecutar FFmpeg con esos argumentos y generar `mezzanine.mp4` a 30 fotogramas por segundo. ✔ Se reproduce.
3. Escucharlo: ¿los cortes se notan? ¿se come alguna sílaba? Ajustar los márgenes si hace falta.
4. Comando de prueba: `uv run content-engine cut video.mp4 transcript.json --from 1203 --to 1330`.

**Terminaste cuando:** cortas un tramo de 45–60 s, sin muletillas ni pausas largas, y no se notan los cortes (experimento 1 de la Fase 0).

---

# Sprint 2 · Prototipo de clip (Fase 0)

**Objetivo:** de tu grabación horizontal a un clip vertical con encuadre a la cara, zooms, subtítulos en Figtree y audio normalizado. La decisión de qué cortar la toma Claude.
**Al final muestras:** 3 clips de un mismo video, comparados con la muestra aprobada del 5 nov, y un informe corto.

### T2.1 · Detectar la cara
`video` · ~8 h
**Lee antes:** `03-edicion-de-clips.md` §5.3 (pasos 1–2).

**Qué vas a construir:** un análisis que dice dónde está la cara de quien habla en cada momento.
**Qué vas a aprender:** leer fotogramas de un video y usar MediaPipe.

1. Instalar MediaPipe y OpenCV. Descargar el modelo de detección de caras.
2. Leer el intermedio a 10 fotogramas por segundo, reducido a 640 px de ancho.
3. Detectar caras en cada fotograma y guardar la caja de la cara (x, y, ancho, alto) con su tiempo.
4. Elegir la cara principal (la más grande y constante).
5. Dibujar la caja sobre algunos fotogramas y guardarlos como imagen. ✔ La caja está sobre la cara.

**Terminaste cuando:** tienes un JSON con la posición de la cara en el tiempo y las imágenes lo confirman.

### T2.2 · Camino de cámara (lógica pura)
`video` · `pruebas` · ~10 h
**Lee antes:** `03-edicion-de-clips.md` §5.3 (pasos 3–7).

**Qué vas a construir:** la función que decide dónde poner la ventana vertical en cada momento para seguir la cara sin temblar.
**Qué vas a aprender:** suavizar movimiento y pensar en coordenadas.

1. Calcular el tamaño de la ventana 9:16 dentro de un video 1920x1080 (608x1080).
2. Centrar la ventana en la cara, sin salirse del cuadro. ✔ Prueba con una cara pegada al borde.
3. **Zona muerta:** si la cara se mueve poco, la ventana no se mueve. ✔ Prueba con movimientos chicos.
4. **Suavizado** y velocidad máxima: la ventana se acerca a la cara poco a poco. ✔ Prueba con un salto grande de la cara.
5. **Zooms:** achicar la ventana hasta 115 % en momentos marcados, con entrada y salida suaves.
6. **Puentes de corte:** en cada corte, alternar entre 100 % y ~110 %.
7. Generar la lista de *keyframes* de recorte (tiempo, x, y, ancho, alto).

**Terminaste cuando:** las pruebas pasan y el camino generado sobre tu grabación se ve estable en un gráfico simple (x en el tiempo).

### T2.3 · Recorte variable con FFmpeg
`video` · ~10 h
**Lee antes:** `03-edicion-de-clips.md` §5.6.

**Qué vas a construir:** el video vertical 1080x1920 que sigue el camino de cámara.
**Qué vas a aprender:** filtros de FFmpeg y cómo darle instrucciones que cambian en el tiempo.

1. Generar el archivo de comandos de tiempo (`sendcmd`) desde los keyframes.
2. Aplicar el filtro de recorte con ese archivo y escalar a 1080x1920. ✔ El video vertical sigue la cara.
3. Revisar que los zooms y los puentes se vean fluidos, sin saltos ni temblores.
4. Si no queda fluido: probar el plan B (recortar cuadro por cuadro en Python con PyAV y pasarlo a FFmpeg) y comparar.
5. Anotar qué opción quedó y por qué.

**Terminaste cuando:** tienes un clip vertical fluido (experimentos 2 y 3 de la Fase 0).

### T2.4 · Subtítulos palabra por palabra
`video` · ~10 h
**Lee antes:** `03-edicion-de-clips.md` §5.4.

**Qué vas a construir:** subtítulos en Figtree, naranja sobre fondo negro, con la palabra actual resaltada.
**Qué vas a aprender:** el formato de subtítulos ASS y cómo FFmpeg los "quema" en el video.

1. Leer la estructura de un archivo ASS: estilos (fuente, tamaño, colores) y eventos (texto con tiempo).
2. Agrupar las palabras en líneas cortas (máx. 4 palabras), cortando en puntuación y pausas. ✔ Prueba con una frase larga.
3. Pasar los tiempos por el **mapa de tiempos** del timeline (T1.5).
4. Generar el resaltado de la palabra actual y la entrada tipo "pop".
5. Ubicar los subtítulos en el tercio inferior, debajo de la cara y fuera de la zona de botones de la plataforma.
6. Quemarlos con FFmpeg usando la fuente Figtree. ✔ Se ven sincronizados con la voz.

**Terminaste cuando:** los subtítulos van sincronizados y nunca tapan la cara (experimento 4).

### T2.5 · Audio a −14 LUFS
`video` · ~4 h

**Qué vas a construir:** el audio del clip con un volumen estándar para redes.
**Qué vas a aprender:** qué es el "volumen percibido" (LUFS) y cómo FFmpeg lo mide y lo ajusta.

1. Medir el volumen del audio actual con FFmpeg.
2. Normalizarlo a −14 LUFS en dos pasadas (primero mide, después ajusta).
3. Verificar el resultado midiendo de nuevo. ✔ Entre −15 y −13.
4. Guidepost no usa efectos de sonido: confirmar que no se agrega nada.

**Terminaste cuando:** el clip final mide −14 ± 1 LUFS (experimento 5).

### T2.6 · Claude decide el clip
`ia` · ~8 h
**Lee antes:** `03-edicion-de-clips.md` §4 y `05-prompts.md` §2 y §3.7.

**Qué vas a construir:** la llamada a Claude que recibe las palabras de un momento y devuelve el JSON de decisiones de edición.
**Qué vas a aprender:** salidas estructuradas de la API de Claude y validación con Pydantic.

1. Crear el modelo Pydantic `EditDecision` (segmentos, hook, énfasis, correcciones de subtítulos).
2. Escribir la primera versión del prompt `clip_decide.md.j2` con las reglas del Edit Spec de Guidepost.
3. Llamar a Claude pidiendo la salida con el esquema del modelo. ✔ Llega un JSON válido.
4. Validar las reglas (rangos, duración 30–60 s, hook ≤ 3 s, sin cifras inventadas) y, si falla, un intento de reparación con los errores.
5. Probar con 3 momentos elegidos a mano.

**Terminaste cuando:** Claude devuelve decisiones válidas para los 3 momentos sin intervención (experimento 6).

### T2.7 · Unir todo y medir
`video` · `documentacion` · ~6 h
**Lee antes:** `03-edicion-de-clips.md` §10.

**Qué vas a construir:** un solo comando que va del video al clip final, y el informe de la Fase 0.

1. Comando `prototype` que encadena: decisión de Claude → timeline → corte → caras → camino → subtítulos → composición → audio.
2. Agregar el logo y el texto del hook si el spec lo pide.
3. Medir cuánto tarda cada parte. ✔ Menos de 3 min por clip (experimento 7).
4. Generar 3 clips y verlos en el celular, junto a la muestra aprobada.
5. Escribir `docs/fase-0-informe.md`: qué funcionó, qué no, tiempos y decisiones (por ejemplo, si quedó `sendcmd` o PyAV).

**Terminaste cuando:** tienes los 3 clips y el informe.

---

# Sprint 3 · Base de datos, login y clientes (Fase 1)

**Objetivo:** la web con login, roles y la gestión de clientes con su perfil y Edit Spec versionados.
**Al final muestras:** el admin crea un operador, crea a Guidepost con su Edit Spec, lo asigna, y el operador solo ve a sus clientes.

### T3.1 · Supabase en tu computadora
`base-de-datos` · `preparacion` · ~4 h

1. `supabase init` y `supabase start`. ✔ Se abre el panel local (Studio) en el navegador.
2. Recorrer el panel: tablas, autenticación, editor de SQL.
3. Crear tu primera migración con una tabla de prueba y aplicarla con `supabase db reset`. ✔ La tabla aparece en el panel.
4. Borrar esa migración de prueba.

**Terminaste cuando:** sabes crear una migración, aplicarla y verla.

### T3.2 · Tablas de usuarios, clientes y perfil
`base-de-datos` · ~8 h
**Lee antes:** `02-modelo-de-datos.md` §3 y §4.1–4.2.

**Qué vas a construir:** las primeras tablas del sistema.
**Qué vas a aprender:** tipos enumerados, claves foráneas (columnas que apuntan a otra tabla) y por qué las versiones no se editan.

1. Migración de tipos enumerados: `user_role`, `client_status`, `asset_kind`.
2. Tablas `profiles`, `client_assignments`, `app_settings`.
3. Tablas `clients`, `baseline_spec_versions`, `client_profile_versions`, `brand_assets`, `profile_examples`.
4. `seed.sql`: un admin, un operador, un revisor, el cliente Guidepost y la primera versión de las reglas base. ✔ `supabase db reset` deja todo cargado.

**Terminaste cuando:** las tablas y los datos de ejemplo se ven en el panel.

### T3.3 · Permisos por fila y sus pruebas
`base-de-datos` · `pruebas` · ~10 h
**Lee antes:** `02-modelo-de-datos.md` §5.1–5.2.

**Qué vas a construir:** las reglas que deciden qué ve cada usuario, y pruebas que lo confirman.
**Qué vas a aprender:** cómo funcionan los permisos por fila y cómo probarlos con pgTAP (pruebas escritas en SQL).

1. Funciones auxiliares `app.my_role()`, `app.is_admin()`, `app.is_assigned()`.
2. Activar los permisos por fila en todas las tablas y escribir las políticas de lectura.
3. Instalar pgTAP y escribir la primera prueba: "un operador ve solo sus clientes". ✔ `supabase test db` pasa.
4. Pruebas para el revisor de video y el admin.
5. Prueba de que nadie puede escribir directo en las tablas.

**Terminaste cuando:** todas las pruebas de permisos pasan.

### T3.4 · Funciones para guardar clientes y perfiles
`base-de-datos` · ~8 h
**Lee antes:** `02-modelo-de-datos.md` §5.3.

1. `upsert_client` y `archive_client` (solo admin). ✔ Prueba: un operador recibe error.
2. `save_profile_version`: crea la versión `n+1` y mueve la versión vigente. ✔ Prueba: dos guardados dejan versiones 1 y 2.
3. `save_baseline_version`.
4. `set_assignment`.
5. Pruebas pgTAP de cada función.

**Terminaste cuando:** las funciones y sus pruebas pasan.

### T3.5 · Proyecto web y login
`web` · ~10 h
**Lee antes:** `06-arquitectura-del-codigo.md` §4.

**Qué vas a construir:** la app Next.js con login por correo y contraseña.
**Qué vas a aprender:** App Router, Server Components, el cliente de Supabase en servidor y navegador, y shadcn/ui.

1. Crear `apps/web` con Next.js, TypeScript estricto y Tailwind. Instalar shadcn/ui.
2. Configurar el cliente de Supabase para servidor, navegador y middleware (el código que revisa la sesión en cada página).
3. Página de login con el formulario de shadcn. ✔ Entras con el usuario del seed.
4. Layout con menú según el rol (el admin ve "Admin", el operador no).
5. Generar los tipos de la base: `supabase gen types`. ✔ El editor autocompleta los nombres de las tablas.
6. Configurar ESLint, Prettier y dependency-cruiser con las reglas de §4.2.

**Terminaste cuando:** cada usuario del seed entra y ve el menú de su rol.

### T3.6 · Admin: usuarios y clientes
`web` · ~10 h

1. Página de usuarios (admin): lista y formulario para crear cuenta, usando una Server Action con la clave de servicio. ✔ Creas un operador nuevo y puede entrar.
2. Página de clientes: lista (filtrada por permisos) y formulario para crear o editar.
3. Asignar operadores y revisores a un cliente.
4. Ver que el operador solo ve sus clientes asignados. ✔ Pruébalo con dos navegadores.

### T3.7 · Perfil y Edit Spec del cliente
`web` · ~10 h
**Lee antes:** `03-edicion-de-clips.md` §2.

**Qué vas a construir:** la pantalla donde el admin edita la voz y el Edit Spec, con historial de versiones.

1. Exportar los modelos Pydantic del spec a JSON Schema y generar los tipos de TypeScript y los esquemas zod (`pnpm gen`).
2. Formulario de la voz (negocio, tono, palabras prohibidas, CTAs, glosario, autor).
3. Formulario del Edit Spec por áreas, con estado confirmado o por confirmar en cada una. Empezar por las áreas que usa la Fase 1 (tono, CTAs, prohibido) y dejar el resto como JSON editable.
4. Cargar el Edit Spec de Guidepost a mano desde `materials/`.
5. Historial de versiones con "ver cambios" y "volver a esta versión".

**Terminaste cuando:** el Edit Spec de Guidepost está cargado y tiene al menos 2 versiones.

---

# Sprint 4 · Subir un video y procesarlo

**Objetivo:** el operador sube un video y ve en vivo cómo avanza hasta tener la transcripción.
**Al final muestras:** subir el video largo de prueba (1 h o más) y ver los pasos cambiar solos en la pantalla.

### T4.1 · MinIO y subida en partes
`web` · `preparacion` · ~10 h
**Lee antes:** `01-arquitectura.md` §8.

**Qué vas a construir:** la subida de videos grandes que se puede retomar si se corta.
**Qué vas a aprender:** almacenamiento compatible con S3, URLs firmadas (enlaces temporales con permiso) y subida en partes.

1. Agregar MinIO a `docker-compose.yml` y crear el bucket privado. ✔ Se abre su panel.
2. Ruta de la web para **iniciar** la subida en partes.
3. Ruta para **firmar** cada parte (cada parte es un pedazo de 64 MB).
4. En el navegador: partir el archivo, subir las partes en paralelo y mostrar el progreso.
5. Ruta para **completar** la subida.
6. Retomar: si se corta, preguntar qué partes ya están y subir solo las que faltan. ✔ Corta el wifi a la mitad y vuelve a conectarlo.

### T4.2 · Tablas de trabajos y pasos
`base-de-datos` · ~6 h
**Lee antes:** `02-modelo-de-datos.md` §4.3 y §4.6.

1. Migración: `jobs`, `transcripts`, `job_steps`, `cost_events`, con sus enums.
2. Permisos por fila y pruebas.
3. Funciones `create_job` y `complete_upload`: la segunda crea los primeros pasos (`probe → extract_audio → transcribe`).
4. Trigger que avisa al worker cuando un paso queda pendiente (`pg_notify`).
5. Activar Realtime en `jobs`.

### T4.3 · La cola del worker
`worker` · `pruebas` · ~12 h
**Lee antes:** `04-worker.md` §2–§3 y §6.

**Qué vas a construir:** el corazón del worker: tomar pasos, avisar que sigue vivo, completar, reintentar.
**Qué vas a aprender:** transacciones, `SKIP LOCKED`, `LISTEN/NOTIFY` y manejo de errores.

1. Conexión con psycopg y repositorios básicos (`adapters/db/`).
2. Consulta para tomar pasos en lote (`04-worker.md` §3.2). ✔ Prueba: dos workers a la vez nunca toman el mismo paso.
3. Escuchar avisos con `LISTEN` y el temporizador para reintentos.
4. Latido y recuperación de pasos de un worker caído. ✔ Prueba: matar el worker a la mitad y ver que otro retoma.
5. Completar un paso en una transacción y liberar a los dependientes.
6. Errores recuperables con espera de 30 s, 2 min y 8 min; errores permanentes sin reintento.
7. Registro de pasos (`registry.py`) y comandos `worker io`, `worker cpu`, `worker maintenance`.
8. Dockerfile del worker y servicios en `docker-compose.yml`.

### T4.4 · Primeros pasos reales: probe, audio y transcripción
`worker` · `ia` · ~8 h

1. Paso `probe`: duración, resolución, audio; reglas de calidad (RF-05). ✔ Un video sin audio falla con un mensaje claro.
2. Paso `extract_audio` (reutiliza T1.4).
3. Paso `transcribe` (reutiliza T1.4), que guarda en `transcripts`.
4. Registrar el costo de AssemblyAI en `cost_events`.

### T4.5 · Pantalla de nuevo trabajo y de progreso
`web` · ~10 h

1. Página "Nuevo trabajo": elegir cliente, nota, mix de piezas y archivo.
2. Página del trabajo con los pasos y su estado.
3. TanStack Query con los datos iniciales del servidor.
4. Suscripción a Realtime que actualiza la pantalla sola. ✔ Ves pasar el trabajo de `queued` a `processing` sin recargar.
5. Aviso de calidad dudosa con botón para confirmar o cancelar.

**Terminaste el sprint cuando:** subes el video largo de prueba y ves la transcripción terminada sin tocar nada.

---

# Sprint 5 · Piezas de texto y revisión

**Objetivo:** generar los posts, el blog y la newsletter, y revisarlos en la pantalla de revisión.
**Al final muestras:** del video largo de prueba, con el perfil de Guidepost, salen las piezas de texto; apruebas unas, comentas otra y se regenera.

### T5.1 · Tablas de piezas, versiones y correcciones
`base-de-datos` · ~6 h
**Lee antes:** `02-modelo-de-datos.md` §4.4.

1. Migración: `pieces`, `piece_versions`, `corrections`, con permisos por fila y pruebas.
2. Funciones `start_review`, `approve_piece`, `add_comment`, `save_manual_edit`.
3. Activar Realtime en `pieces` y `piece_versions`.

### T5.2 · Prompts como archivos
`ia` · ~6 h
**Lee antes:** `05-prompts.md` §2 y §6.

1. Cargador de prompts: lee el archivo, su encabezado (versión, modelo) y arma el texto con Jinja2.
2. Bloques compartidos: system, contexto del cliente y fuente (transcripción con índices y minutos).
3. Adaptador de Claude con caché de prompts y registro de tokens y costo.
4. Control del tope de costo por video antes de cada llamada.

### T5.3 · Elegir momentos
`ia` · `worker` · ~8 h
**Lee antes:** `05-prompts.md` §3.1.

1. Prompt `select_moments.md.j2` y su modelo de salida.
2. Validación: cantidades del mix, temas sin repetir, rangos existentes.
3. Paso `select_moments`: crea las piezas y sus pasos con el planificador (`04-worker.md` §4.2).
4. ✔ Prueba con la transcripción de T1.4: las ideas tienen sentido y no se repiten.

### T5.4 · Generar posts, blog y newsletter
`ia` · `worker` · ~10 h
**Lee antes:** `05-prompts.md` §3.2–3.4.

1. Prompt y modelo de salida de **post** por plataforma.
2. Prompt y modelo del **blog**; plantillas para Markdown, HTML y el schema FAQPage.
3. Prompt y modelo de la **newsletter**; plantilla de texto y HTML.
4. Paso `text.generate`, que guarda la versión de la pieza con el prompt y el modelo usados.

### T5.5 · Que no invente datos
`ia` · `pruebas` · ~6 h
**Lee antes:** `05-prompts.md` §4.

1. Extraer cifras, porcentajes, montos y fechas de un texto. ✔ Pruebas con varios formatos ("60%", "sixty percent").
2. Comprobar que cada una aparezca en la transcripción o en el perfil.
3. Paso `validate` (versión de Fase 1) que marca la pieza si algo no aparece.

### T5.6 · Pantalla de revisión
`web` · ~12 h

1. Tarjetas de las piezas con vista previa, minuto de origen y estado.
2. Aprobar.
3. Editar el texto a mano.
4. Comentar, marcando si es del cliente (con sus palabras) o interno, y regenerar.
5. La versión anterior se sigue viendo mientras se regenera; al terminar, la tarjeta se actualiza sola.
6. Que se vea bien en el celular (RNF-07).

### T5.7 · Regenerar
`worker` · `ia` · ~4 h
**Lee antes:** `05-prompts.md` §3.9 y `04-worker.md` §7.1.

1. Bloque de regeneración en el prompt (versión anterior + comentario).
2. Cancelar una regeneración anterior pendiente de la misma pieza.
3. ✔ Medir: regenerar un post tarda menos de 1 min (RNF-02).

---

# Sprint 6 · Entregar, historial y prueba real (cierre de Fase 1)

**Objetivo:** cerrar el ciclo completo con un video real.
**Al final muestras:** la demo de la Fase 1, con un operador que genera, revisa y envía las piezas de texto de un video real.

### T6.1 · Paquete y link compartible
`worker` · `web` · ~10 h
**Lee antes:** `01-arquitectura.md` §9.1.

1. Migración: `packages`, `package_shares`; funciones `deliver_job`, `create_share`, `revoke_share`.
2. Paso `deliver`: ZIP ordenado por formato.
3. Página pública `/p/{token}` con descargas por URLs firmadas de pocos minutos.
4. Revocar y vencer links. ✔ Un link revocado ya no abre.

### T6.2 · Historial por cliente
`web` · ~6 h

1. Página del cliente con sus trabajos, piezas, estados y quién aprobó (RF-19).
2. Ver las versiones de una pieza y sus correcciones.
3. Marcar una pieza aprobada como ejemplo (admin).

### T6.3 · Reintentar y cancelar
`worker` · `web` · ~6 h
**Lee antes:** `04-worker.md` §7.

1. Funciones `retry_job`, `retry_piece`, `cancel_job`, `resume_job`.
2. Botones en la pantalla.
3. El worker detiene un paso en curso al cancelar.

### T6.4 · Mantenimiento y pruebas de punta a punta
`worker` · `pruebas` · ~8 h

1. Proceso `worker maintenance`: recuperar pasos, avisar trabajos trabados.
2. Prueba de punta a punta con Playwright: login, subir video corto, revisar, aprobar, enviar.
3. CI en GitHub Actions con los jobs de `06-arquitectura-del-codigo.md` §11.

### T6.5 · Prueba con un video real y demo
`documentacion` · ~10 h

1. Procesar de punta a punta un video real del cliente (crudo, de más de 1 h). Si la agencia todavía no lo comparte, usar el video largo de prueba y anotar en la lista de pendientes que falta la validación con un video real.
2. Medir: de fin de subida a piezas listas (meta: menos de 60 min para un video de 1 h).
3. Grabar la demo de la Fase 1.
4. Actualizar la documentación: cómo instalar y cómo editar los prompts (RNF-10, versión inicial).
5. Lista de lo aprendido y lo pendiente para la Fase 2.

**Terminaste la Fase 1 cuando:** un operador genera y envía las piezas de texto de un video real sin ayuda técnica.

---

## Fases 2, 3 y 4

Se planifican **cuando terminen la Fase 0 y la Fase 1**, con el mismo formato de este documento. Para entonces ya se sabrá cómo quedó el recorte de video, cuánto tarda cada clip y el ritmo real de trabajo. Contenido de cada fase: `00-resumen-decisiones.md` (Fases) y el requerimiento.

## Pendientes de confirmar con la agencia

- El requerimiento dice que la Fase 1 se aprueba con "las **12** piezas de texto". Con el mix actual son 8 (6 posts, 1 blog, 1 newsletter). Puede que cuenten también los copys de clips, carruseles y citas. Confirmarlo antes de la demo.
- El formato AEO de blog y newsletter (`05-prompts.md` §1).
- Los gráficos animados quedan fuera de alcance (`03-edicion-de-clips.md` §11).

## Cobertura de la Fase 1

| Requisito | Tareas |
| --- | --- |
| RF-01 Login y roles | T3.2, T3.3, T3.5, T3.6 |
| RF-02 Clientes y perfil versionado | T3.2, T3.4, T3.7 |
| RF-04 Subida reanudable | T4.1 |
| RF-05 Validar archivo | T4.4, T4.5 |
| RF-06 Transcripción | T1.4, T4.4 |
| RF-07 Elegir momentos | T5.3 |
| RF-08 Piezas de texto | T5.4 |
| RF-12 Pantalla de revisión | T5.6 |
| RF-13 Regenerar con comentario | T5.6, T5.7 |
| RF-16 Envío del paquete | T6.1 |
| RF-19 Historial | T6.2 |
| RNF-03 Reintentos | T4.3, T6.3 |
| RNF-04 Seguridad | T1.2 (claves fuera del repo), T3.3, T4.1 (bucket privado) |
| RNF-05 Costos y tope | T4.4, T5.2 |
