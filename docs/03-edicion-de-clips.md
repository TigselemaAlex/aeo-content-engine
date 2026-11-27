# 03 · Edit Spec, JSON de decisiones de edición y pipeline de clips

**Proyecto:** Content Engine (AEO.co) · **Fecha:** 12 de noviembre de 2026 · **Autor:** Alex Tigselema
**Fuentes:** documento de requerimientos (RF-10, RF-11, RF-13, RF-14, RF-15), `ref_client-video-editing-rules.md` (reglas base de la agencia y plantilla), `bkb_edit-spec_guidepost-marketing-real-example.md` (Edit Spec real), documentos 00 a 02.

Define cómo se guarda el Edit Spec, qué JSON devuelve Claude para cada clip y cómo el worker lo convierte en un MP4 con FFmpeg y MediaPipe. Cubre también la regeneración por aspecto, la revisión automática y los experimentos de la Fase 0.

---

## 1. Decisiones de este documento

| Tema | Decisión | Origen |
| --- | --- | --- |
| Modelo del Edit Spec | **Reglas base de la agencia + Edit Spec del cliente que las sobrescribe**, igual que el proceso actual. Las reglas base son globales, versionadas y las edita el admin | `ref_client-video-editing-rules.md`: "if a client rule says something different, the client rule wins" |
| Áreas del Edit Spec | Las 15 áreas de la plantilla de la agencia, mapeadas a los 9 bloques del requerimiento | Plantilla de la agencia; requerimiento §Perfil |
| Cada área | Parámetros que la máquina aplica + reglas en texto que lee Claude + estado `confirmed` / `to_confirm` | Los Edit Specs reales mezclan valores exactos y reglas cualitativas, y tienen campos "[To confirm]" |
| Campos sin confirmar | Usan el valor de las reglas base y se muestran como pendientes en la ficha del cliente | Guidepost tiene 8 campos "[To confirm]" |
| Gráficos animados explicativos | **Fuera de alcance.** Si un cliente los pide (Guidepost), los agrega el revisor de video | Respuesta del 12 nov; RF-10 no los incluye |
| Duración | 30 a 60 s por defecto; el cliente puede extender hasta 90 s | Respuesta del 12 nov: reglas base "under 60 s" + requerimiento "30 a 90 s" |
| Hook | Texto en pantalla con la palabra clave resaltada y, si Claude lo considera mejor, el clip arranca con una frase fuerte de más adelante del mismo momento (*cold open*) | Respuesta del 12 nov; reglas base: "open with the question or the most surprising line" |
| Origen del comentario | Cada corrección indica si es feedback del cliente (con sus palabras) o interno | Respuesta del 12 nov; change log de la agencia |
| Prioridad de reencuadre | Una persona a cámara, grabación horizontal | Respuesta del 12 nov; Guidepost: "solo to camera, records horizontally" |
| Claude y el tiempo | Claude solo referencia **índices de palabras** de la transcripción, nunca milisegundos ni píxeles | Principio "Claude decide, el worker ejecuta"; evita tiempos inventados |

---

## 2. El Edit Spec

### 2.1 Reglas base + cliente

```mermaid
flowchart LR
  B[Reglas base de la agencia<br/>baseline_spec_versions] --> M{Combinar}
  C[Edit Spec del cliente<br/>client_profile_versions.edit_spec] --> M
  M --> E[Spec efectivo<br/>congelado en jobs.effective_spec]
  E --> D[Claude: decisiones]
  E --> R[Worker: render]
  E --> V[Revisión automática]
```

Reglas de combinación, por área:

| Elemento | Regla |
| --- | --- |
| `params` | El valor del cliente gana por campo. Si el área del cliente está `to_confirm`, se usan los `params` base. |
| `rules` (texto) | Se juntan: primero las base, después las del cliente. Si el cliente marca una regla base como reemplazada (`overrides`), esa regla base no se envía. |
| `never_do` | Unión de base y cliente. |
| `qc_extras` | Unión. |

El trabajo guarda el resultado en `jobs.effective_spec` al crearse, junto con las dos versiones usadas. Así una pieza siempre se puede reproducir aunque después cambien las reglas.

### 2.2 Estructura

```json
{
  "schema_version": 1,
  "references": [
    { "title": "Muestra aprobada del 5 nov", "url": null, "note": "Estándar de producción" }
  ],
  "areas": {
    "captions": {
      "status": "confirmed",
      "params": { "font_asset_id": "…", "text_color": "#FF7B2A", "background": { "enabled": true, "color": "#000000" } },
      "rules": ["Grupos cortos de subtítulos", "Énfasis selectivo en las palabras que Kyle está diciendo"],
      "overrides": [],
      "evidence": "Slack, 4 nov"
    }
  },
  "never_do": [
    { "rule": "Efectos de sonido", "check": "auto" },
    { "rule": "Gráficos decorativos sin significado", "check": "manual" }
  ],
  "qc_extras": ["Comparar lado a lado con la muestra aprobada del 5 nov"]
}
```

`check` indica cómo se verifica en la revisión automática (§7): `auto` (el worker lo comprueba con datos del render), `llm` (lo revisa Claude Haiku) o `manual` (queda en la lista del operador).

### 2.3 Áreas y parámetros

La columna **Bloque** es el del requerimiento. Los valores por defecto salen de las reglas base de la agencia (short form).

| Área (plantilla de la agencia) | Bloque | `params` que aplica la máquina | Base por defecto | Lo usa |
| --- | --- | --- | --- | --- |
| `format_length` | Exportación / Ritmo | `aspect`, `min_seconds`, `max_seconds` (tope 90) | 9:16, 30–60 s | Claude, timeline |
| `hook` | Apertura y cierre | `max_seconds`, `text_on_screen`, `emphasize_keyword`, `keyword_style` (color, escala), `allow_cold_open` | 3 s, sí, sí, color de acento, sí | Claude, subtítulos |
| `pacing` | Ritmo | `visual_change_every_s` [mín, máx], `max_static_s`, `pause_max_ms`, `keep_emphasis_pauses`, `remove_fillers`, `j_cut_frames` [mín, máx], `cut_bridge` (`none`, `punch_in`) | [2, 3], 4, 500, sí, sí, [3, 5], `punch_in` | Timeline, encuadre |
| `camera_framing` | Visual | `layout` (`speaker_crop`, `fit_blur`), `keep_face_visible`, `zoom.enabled`, `zoom.max_scale`, `zoom.ease_s` [mín, máx] | `speaker_crop`, sí, sí, 1.15, [1, 2] | Encuadre |
| `captions` | Subtítulos | `font_asset_id`, `size_px`, `text_color`, `background`, `outline`, `highlight.mode` (`word`, `keywords`, `none`), `highlight.color`, `position` (`lower_third`), `max_words_per_line`, `max_chars_per_line`, `max_lines`, `uppercase`, `animation_in` (`pop`, `fade`, `none`), `avoid_face`, `platform_safe_zone` | sans serif, tercio inferior, 1 línea, entrada pop, sin salida, zona segura | Subtítulos |
| `fonts_colors` | Marca | `font_asset_ids`, `palette` (nombre → HEX), `forbidden_fonts` | — | Subtítulos, hook, tarjeta final |
| `logo` | Marca | `asset_id`, `position`, `width_pct`, `margin_pct`, `visibility` (`always`, `none`) | `none` hasta que el cliente lo defina | Composición |
| `broll_assets` | Visual | `enabled`, `sources`, `darken_under_text` | apagado (P1) | — en el MVP |
| `music_sound` | Audio | `music.enabled`, `music.asset_ids`, `music.volume_db`, `music.ducking`, `sfx.enabled`, `sfx.max_per_minute`, `sfx.asset_ids`, `loudness_lufs`, `true_peak_db` | música sí, −22 dB con ducking; sfx sí, máx 3/min; −14 LUFS, −1 dBTP | Audio |
| `graphics_transitions` | Visual | `transitions` (`cut`, `fade`, `zoom`), `forbidden_transitions`, `emojis` | `cut`, —, no | Composición |
| `tone` | — | — (solo `rules`) | — | Claude |
| `cta_end_screen` | Apertura y cierre | `intro_asset_id`, `outro_asset_id`, `end_card.enabled`, `end_card.template_asset_id`, `end_card.text`, `end_card.seconds`, `caption_cta` | sin intro (regla base: "no intro, no greeting"), tarjeta final no, `caption_cta` "Full video in the comments" | Composición, copy |
| `templates` | Plantillas gráficas | `carousel_template_asset_id`, `quote_template_asset_id` | — | Carruseles y citas |
| `export` | Exportación | `resolution`, `fps`, `video_codec`, `audio_codec`, `max_size_mb`, `file_naming` | 1080x1920, 30, H.264, AAC, 100, `{client}_{topic}_v{n}` | Composición, verificación |
| `delivery` | — | — (solo `rules`) | — | Paquete |
| `never_do` | Prohibido | lista con `check` | — | Todo |

Ejemplo, Guidepost aplicado a este modelo: `music_sound.sfx.enabled = false` y `pacing.cut_bridge = "punch_in"` ("bridge cuts with subtle reframing"). En `captions` van Figtree, `text_color #FF7B2A` y `background.color #000000`, y desde la T2.4 (elegidos por Alex sobre el tramo de prueba) `size_px 72` en Bold, `highlight.mode word` con `highlight.color #FFFFFF`, `max_words_per_line 4`, `max_chars_per_line 22` y `uppercase false` (§5.4). En `fonts_colors.forbidden_fonts` va `["Phudu"]`. Con `avoid_face`, `position lower_third` se resuelve como "debajo de la cara", y `platform_safe_zone` solo avisa cuando la cara no deja lugar (§5.4, §5.7). En la Fase 0 el estilo de los subtítulos está fijo en `CaptionStyle` (`captions_ass.py`), que además usa valores que la tabla todavía no lista: `bold`, `box_padding_px` (18), `pop_from` (0,8), `pop_ms` (80) y `face_gap_px` (20). El Edit Spec lo alimenta desde la Fase 1; si esos valores pasan a ser parámetros del spec, se agregan a la fila `captions`. `logo`, `hook` y `export.resolution` quedan `to_confirm` y usan las reglas base.

### 2.4 Lo que el MVP no aplica aunque esté en el Edit Spec

| Regla del Edit Spec | Qué pasa |
| --- | --- |
| Gráficos animados que explican (diagramas, búsquedas, tarjetas) | Fuera de alcance. Queda como regla `manual` para el revisor de video. |
| Layout con gráficos arriba y la persona abajo | Fuera de alcance (depende de los gráficos). |
| B-roll | P1. |
| Imágenes aprobadas del cliente (por ejemplo, imágenes de Kyle generadas con IA) | Llegan con el B-roll (P1). |
| Varias cámaras o pantalla dividida con dos personas (ejemplo Jamie Anne) | No en el MVP: la entrada es un solo video. Dos personas en el mismo plano sí se contemplan (§5.5). |
| Formatos de salida por plataforma (16:9, 1:1) | El requerimiento pide solo 9:16. |

---

## 3. Entradas de un clip

Cuando el worker procesa un clip, ya tiene:

| Entrada | De dónde | Contenido |
| --- | --- | --- |
| Momento | `pieces` (paso `select_moments`) | `idea`, `selection_reason`, `source_ranges` (en ms y en índices de palabra) |
| Palabras | `transcripts.words` | texto, `start_ms`, `end_ms`, hablante, confianza, y si es muletilla (*disfluency*) |
| Spec efectivo | `jobs.effective_spec` | §2 |
| Medios | `jobs.media` | resolución, fps, duración |
| Recursos | `brand_assets` | fuentes, logo, música, sfx, plantillas |
| Comentario | `corrections` | solo en regeneraciones |

La transcripción se pide a AssemblyAI con las muletillas incluidas (*disfluencies*) y con el vocabulario del cliente (nombres de marca, productos) para que se escriban bien. El vocabulario sale de `voice.glossary`, un campo nuevo del perfil, y se envía como `keyterms_prompt`. AssemblyAI no marca qué palabras son muletillas: el adaptador las marca con `is_disfluency` usando la lista del dominio de `ingest` (decisión "Muletillas y glosario" en `00`).

---

## 4. JSON de decisiones de edición

Claude recibe las palabras del momento con su índice, por ejemplo `[1203] Google [1204] stopped …`, más el spec efectivo, y devuelve un único JSON validado con `schemas/edit_decision.json`.

### 4.1 Ejemplo

```json
{
  "schema_version": 1,
  "title": "Why Google stopped sending traffic",
  "segments": [
    { "from_word": 1268, "to_word": 1281, "role": "hook" },
    { "from_word": 1203, "to_word": 1267, "role": "body" },
    { "from_word": 1282, "to_word": 1330, "role": "body" }
  ],
  "extra_cuts": [
    { "from_word": 1241, "to_word": 1246, "reason": "Repite la idea anterior" }
  ],
  "keep_pauses": [
    { "after_word": 1259, "reason": "Pausa de énfasis antes de la respuesta" }
  ],
  "hook": {
    "text": "Google isn't sending you traffic anymore",
    "keywords": ["Google"]
  },
  "emphasis": [
    { "word": 1230, "kind": "zoom" },
    { "word": 1301, "kind": "zoom" },
    { "word": 1215, "kind": "caption_keyword" },
    { "word": 1290, "kind": "caption_keyword" }
  ],
  "caption_fixes": [
    { "word": 1219, "text": "AEO" }
  ],
  "story": {
    "hook_word": 1268,
    "tension_word": 1255,
    "answer_word": 1290,
    "cta_word": null
  },
  "end_cta_text": "Full video in the comments",
  "rationale": "El hook adelanta la frase más fuerte; la tensión está en el 'but' de 1255."
}
```

### 4.2 Campos

| Campo | Qué es | Reglas de validación |
| --- | --- | --- |
| `segments` | Tramos del momento, en el orden en que se verán | Dentro del rango del momento (± 15 s de margen); sin solaparse. Como máximo un `hook`, y si existe va primero. El primer `body` puede empezar antes que el hook (*cold open*). Solo si `hook.allow_cold_open`. |
| `extra_cuts` | Partes que Claude quiere quitar además de muletillas y pausas | Dentro de algún segmento. |
| `keep_pauses` | Pausas que no se deben recortar (énfasis) | Solo si `pacing.keep_emphasis_pauses`. |
| `hook.text` | Texto del hook en pantalla | Máx. ~8 palabras. **No puede tener cifras ni nombres que no estén en la transcripción** (regla "no inventa datos"). |
| `hook.keywords` | Palabras del hook con estilo distinto | Deben estar en `hook.text`. |
| `emphasis` | Momentos de zoom y palabras resaltadas en subtítulos | Zooms con al menos 4 s de separación; cantidad acorde a `pacing`. |
| `caption_fixes` | Corrección de cómo se escribe una palabra en el subtítulo | Solo ortografía: distancia de edición pequeña o término del glosario. **No cambia lo que se dijo.** |
| `story` | Marca dónde están hook, tensión, respuesta y CTA (estructura de la agencia) | Índices dentro de los segmentos; sirve para la revisión y para explicar la elección. |
| `end_cta_text` | Texto de cierre o del copy | Viene de los CTAs aprobados del perfil o de `caption_cta`. |
| `rationale` | Por qué se armó así | Se muestra al operador. |

### 4.3 Validación y reparación

1. Validación de esquema (Pydantic).
2. Validación de reglas (tabla anterior) **y de duración**: se calcula el timeline (§5.1) y la duración final debe estar entre `min_seconds` y `max_seconds`.
3. Si algo falla, se le devuelven a Claude los errores concretos ("dura 72 s, máximo 60") para **un** intento de reparación. Si vuelve a fallar, la pieza queda `failed` con el error visible.

Claude no decide estilos (fuentes, colores, posición del logo): eso lo aplica el worker desde el spec. Así una pieza nunca puede salir con una tipografía prohibida por decisión del modelo.

---

## 5. Pipeline de render

Cada clip es un grupo de pasos en `job_steps`. En la cola, *timeline* corre dentro de `clip.extract` y *overlays* dentro de `clip.compose` (`04-worker.md` §4.1), porque son rápidos y no conviene pagar un paso aparte por ellos. Los resultados intermedios se guardan en `work/{job_id}/clips/{piece_id}/` con un hash de sus entradas, para no rehacer lo que no cambió (§6).

```mermaid
flowchart TD
  A[1 · decide<br/>io · Claude → JSON] --> B[2 · timeline<br/>código puro]
  B --> C[3 · extract<br/>cpu · FFmpeg]
  C --> D[4 · analyze<br/>cpu · MediaPipe]
  B --> E[5 · overlays<br/>subtítulos ASS, hook, logo]
  D --> E
  D --> F[6 · compose<br/>cpu · FFmpeg]
  E --> F
  F --> G[7 · verify<br/>ffprobe, loudness, vista previa]
  G --> H[validate<br/>revisión automática §7]
```

### 5.1 Timeline (código puro, sin red ni archivos)

Convierte el JSON de decisiones en una lista de cortes del video original y en un **mapa de tiempos** (tiempo en el original → tiempo en el clip).

1. Toma los `segments` en orden.
2. Quita las muletillas (si `remove_fillers`) y los `extra_cuts`.
3. Parte el tramo en cada pausa mayor a `pause_max_ms`, salvo las de `keep_pauses`, igual que con una muletilla. No hay una duración de pausa propia: el silencio que queda lo forman los márgenes del punto 4 (≈ 120 + 60 = 180 ms).
4. Ajusta cada corte al borde de palabra con un margen (≈ 60 ms antes, ≈ 120 ms después) para no cortar sílabas. Nunca corta en medio de una palabra.
5. Aplica *J cuts*: en cada unión, el audio del tramo siguiente entra `j_cut_frames` antes que la imagen. Se usa el valor del medio del rango, siempre el mismo (`(mín + máx) // 2`: 4 fotogramas ≈ 133 ms a 30 fps), para que el paso dé el mismo resultado al repetirse. Los cortes de audio no cambian; el timeline guarda aparte los cortes de imagen (`video_cuts`): en cada unión, la imagen del corte anterior se alarga ese tiempo y la del siguiente empieza ese tiempo después. Los cortes del medio duran lo mismo que su audio (el primero dura ese tiempo más y el último ese tiempo menos), así que la imagen suma lo mismo que el audio y no se desfasan, y el mapa de tiempos se calcula sobre el audio, que es lo que siguen los subtítulos.
6. Marca qué cortes necesitan "puente" (`cut_bridge`): en una sola cámara, un salto se disimula cambiando el encuadre (§5.3).
7. Devuelve la lista de tramos, el mapa de tiempos, la duración final y la lista de puntos de corte.

Es la parte con más lógica y la más fácil de probar: tests unitarios con transcripciones de ejemplo, sin video.

### 5.2 Extract

FFmpeg extrae cada tramo del original con búsqueda exacta y los une en un **intermedio** (`mezzanine.mp4`): resolución original, 30 fps constantes, H.264 de alta calidad (CRF 16, preset `veryfast`, `yuv420p`) y audio AAC a 48 kHz y 192 kbps. Los siguientes pasos trabajan sobre este archivo corto, no sobre el video de 1 hora.

Por los J cuts, la imagen y el audio de cada tramo tienen rangos distintos (`video_cuts` y `cuts`, §5.1). Cada rango es una entrada propia de FFmpeg con búsqueda de entrada (`-ss inicio -t duración -i original`): dos entradas por tramo, imagen y audio. **La imagen y el audio se unen por separado** (un `concat` de solo imagen y otro de solo audio): si se unieran de a pares, cada tramo duraría lo del más largo y `concat` rellenaría el otro con silencio o imagen congelada, deshaciendo el J cut. Cada tramo de imagen se lee 100 ms de más, se pasa a 30 fps y se recorta (`trim=end_frame`) a un número exacto de fotogramas, redondeado sobre el tiempo **acumulado**: el tramo k termina en el fotograma `round(fin acumulado × 30 ÷ 1000)`. Así cada corte queda a menos de medio fotograma de su lugar sin que el error se sume, aunque el original tenga otra frecuencia (24 fps, por ejemplo, donde FFmpeg solo entrega fotogramas enteros de 41,7 ms), y el camino de cámara ubica los puentes con la misma cuenta. Los 100 ms de más aseguran que siempre haya fotogramas para recortar: por el redondeo acumulado un tramo puede necesitar hasta 1 fotograma más que su propia duración (33,3 ms), y con un original a 24 fps la lectura puede quedarse corta un fotograma entero (41,7 ms); el peor caso es 33,3 + 41,7 = 75 ms. Comprobado: un tramo de 1035 ms que debe dar 32 fotogramas sale con 31 si no se lee nada de más, y con 32 si se leen 100 ms. Al terminar, `clip.extract` cuenta los fotogramas del intermedio con `ffprobe` y falla con `PermanentError` si no son exactamente `round(duración × 30 ÷ 1000)`: puede pasar si el tramo llega al final del original y los 100 ms de más no se pueden leer, y repetir el paso daría lo mismo (decidido el 26 nov 2026). Saltar al punto exacto evita leer el original desde el principio, como haría recortar con `trim`/`atrim` sobre una sola entrada. Los argumentos los arma una función pura del dominio del clip (`ffmpeg_args.py`); el adaptador solo ejecuta FFmpeg.

### 5.3 Analyze: encuadre

Sobre el intermedio, reducido a ~640 px de ancho:

1. **Detección de cara** con MediaPipe Face Detector, ~10 fps. Las cajas se guardan en píxeles del intermedio original, no de la imagen reducida, y no se recortan al cuadro: si la cara se sale en parte, `x` o `y` pueden ser negativos (visto en la grabación de prueba, T2.1).
2. **Pista principal:** en una persona a cámara es la cara más grande y persistente. Las caras se agrupan en pistas: una caja se une a la pista más cercana si su centro está a ≤ 0,5 anchos de cara de la última caja de esa pista y es de un fotograma anterior, sin límite de tiempo. Gana la pista con mayor suma de áreas (ancho × alto de cada caja).
3. **Ventana 9:16:** alto completo y ancho = alto × 9 ÷ 16, calculado desde la resolución real del intermedio. En un video 1920x1080 da 608x1080.
4. **Camino de cámara** (código puro, `camera_path.py`): un keyframe por fotograma del intermedio (30 fps). Entre dos cajas de cara (cada 100 ms) la posición se interpola en línea recta, salvo a través de un corte: ahí cada lado usa la caja de su plano. El centro de la ventana sigue a la cara con:
   - zona muerta: no se mueve mientras el centro de la cara esté dentro del 10 % central **del lado de la ventana en cada eje**: del ancho en horizontal (±30 px en 608) y del alto en vertical (±49 px en 982). Al salir, apunta a centrar la cara. Sin zoom la ventana ocupa todo el alto y no se mueve en vertical; la zona vertical solo cuenta en puentes y zooms, donde sobra más espacio que en horizontal,
   - suavizado con un resorte amortiguado crítico (ω = 8, llega en ~0,6 s sin pasarse) y velocidad máxima de 600 px/s (20 px por fotograma),
   - límites para que la cara quede visible (`keep_face_visible`): se permite dejar afuera hasta un **5 % del lado de la caja en cada eje, por lado** (del ancho en horizontal, del alto en vertical), para que el ruido de los bordes de la detección no haga temblar la ventana. Si aun así la cara no cabe, la ventana se centra en ella. Esta regla gana sobre la velocidad máxima.
   - cuando esta regla (o el borde del cuadro) mueve la ventana, el resorte se detiene ahí y apunta a ese lugar. Si no, la zona muerta, que compara la cara con la cámara ya empujada junto a ella, conservaba un objetivo viejo; el resorte tiraba en contra del empuje y la ventana copiaba el ruido del borde de la caja (6 vaivenes de 2–8 px en la salida sobre el tramo de prueba; con la regla, 0 y un 22 % menos de recorrido de la cámara; decidido el 26 nov 2026, T2.3).
5. **Zooms:** en cada `emphasis.kind = zoom`, la ventana se achica hasta `zoom.max_scale` (1.15): entrada de 1,5 s (el medio de `zoom.ease_s`), 1 s sostenido y salida de 1,5 s. En total 4 s, la separación mínima entre zooms. Las curvas usan *smoothstep* (3p² − 2p³). Los índices de palabra se pasan a tiempo del clip antes (`words_to_clip_ms` en el timeline).
6. **Puentes de corte** (`cut_bridge = punch_in`): en cada salto de imagen (`Timeline.video_cut_points_ms`), el encuadre alterna al instante entre 100 % y 110 % y la cámara salta a la cara, así el corte se lee como cambio de plano y no como salto. Con un zoom en curso: escala = base + (1,15 − base) × avance del zoom; con el zoom completo el puente no se nota. Esto también cumple el "cambio visual cada 2–3 s" de las reglas base.
7. **Sin cara** más de 2 s (por ejemplo, se sale de cuadro): se mantiene la última posición, y el camino devuelve esos tramos (todo el hueco, `no_face`) para que el render use `fit_blur` (cuadro completo centrado sobre el mismo video desenfocado). Un hueco es más de 200 ms entre dos cajas.

Ancho y alto de la ventana se redondean a números pares (`yuv420p`). La posición se redondea por el **centro**: primero el centro a píxel entero y después el borde, centro − lado ÷ 2 (exacto porque el lado es par). Redondear el borde por su cuenta hacía que, con el centro en 490,5 y el alto creciendo de a 2 px al salir de un zoom, el centro alternara 490 ↔ 491 (T2.3). El fotograma de cada corte es `round(ms × 30 ÷ 1000)`, la misma cuenta con la que el intermedio recorta sus tramos (§5.2), y hay un keyframe por fotograma real: `round(duración × 30 ÷ 1000)`.

Resultado: una lista de *keyframes* de recorte `(t, x, y, w, h)`, los tramos sin cara y la caja de la cara por tiempo, que sirve para ubicar los subtítulos (`avoid_face`) y para la revisión automática.

### 5.4 Overlays

| Elemento | Cómo |
| --- | --- |
| Subtítulos | Archivo ASS generado desde las palabras y el mapa de tiempos. Agrupa por `max_words_per_line`, puntuación y pausas. Resalta palabra por palabra o solo `caption_keyword`, según `highlight.mode`. Entrada pop (escala 80 % → 100 % en ~80 ms), sin salida. Fondo de caja si `background.enabled`. Se ubica en el tercio inferior por debajo de la cara (20 px bajo la barbilla); si eso la saca de la zona segura de las plataformas, gana la cara y la zona segura solo avisa (§5.7). Detalle en "Subtítulos (T2.4)", debajo de esta tabla. |
| Hook | Capa ASS de 0 a `hook.max_seconds` con `hook.text`; las `keywords` usan `keyword_style`. |
| Logo | PNG escalado a `width_pct` × 1080 px en `position` con `margin_pct`. |
| Tarjeta final | Si `end_card.enabled`: PNG renderizado con Playwright desde la plantilla del cliente (mismo motor que carruseles). |
| Fuentes | Las del cliente se copian a una carpeta de fuentes del render; si falta una, el paso falla (no cae en una fuente por defecto). En la Fase 0 la carpeta es `worker/assets/fonts/` (Figtree-Bold.ttf v2.0.3 de erikdkennedy/figtree con su `OFL.txt`; la licencia OFL 1.1 permite versionarla junto a su licencia), que `compose` copia a su carpeta temporal y pasa al filtro `ass` con `fontsdir`. libass **no falla** si falta la fuente: cae en otra del sistema (`(Figtreee, 700, 0) -> Arial-BoldMT`, medido el 26 nov 2026). Por eso `compose` dibuja antes los subtítulos en chico (270x480), lee qué fuente eligió libass (`fontselect`, visible con `-v debug`) y se detiene si no es de la familia del estilo o, si el estilo es negrita, si el nombre de la fuente elegida no dice Bold, SemiBold, ExtraBold, Black o Heavy (libass simularía la negrita con la regular; decidido por Alex el 26 nov 2026). El estilo se lee del propio ASS. |

**Subtítulos (T2.4, 26 nov 2026).** El dominio (`captions_ass.py`) arma el ASS; el adaptador solo lo quema. Estilo de Guidepost elegido por Alex sobre fotogramas reales del tramo de prueba:

1. **Palabras del clip:** las que no son muletillas y caben enteras en un tramo de audio (`Timeline.cuts`); su tiempo es el del mapa de tiempos del audio, así que los subtítulos siguen a la voz también en los J cuts ("you" se resalta en el fotograma 94 y la imagen cambia en el 96).
2. **Frases y líneas:** una frase termina en puntuación de cierre, en cada corte del timeline (se quitó una muletilla o una pausa) o en un silencio de más de 500 ms (`pause_max_ms`). Cada frase se parte en la menor cantidad de líneas de hasta 4 palabras y 22 caracteres; entre las que tienen esa cantidad gana la de la línea más larga más corta ("you basically" / "don't exist.", 13 y 12, en vez de 22 y 3). Una palabra de más de 22 caracteres va sola. Tramo de prueba: 78 palabras en 27 líneas. 22 caracteres porque con Figtree Bold 72 'Answer Engine Optimization.' (27) mide 840 px, unos 840 ÷ 27 ≈ 31 px por carácter, y el ancho útil centrado en x = 540 sin la columna de botones de la derecha es 2 × (888 − 540) = 696 px: 696 ÷ 31 ≈ 22.
3. **Tiempos:** cada palabra se resalta desde el fotograma más cercano a su inicio, `round(ms × 30 ÷ 1000)`, hasta el de la palabra siguiente; la última línea sigue hasta el final del clip. El evento ASS empieza medio fotograma antes, `(n − 0,5) ÷ 30` s, escrito en centésimas: libass lo muestra desde el primer fotograma en ese tiempo o después, y el medio fotograma absorbe el redondeo a centésimas (mismo motivo que `sendcmd`, §5.6). El desfase con el inicio de la palabra queda en ±½ fotograma (16,7 ms). Si dos palabras caen en el mismo fotograma (la transcripción completa tiene "a" de 16 ms), la primera no se resalta, pero se ve en la línea. Si ninguna palabra de una línea llega a tener su fotograma (por ejemplo, una línea de una sola palabra corta), la línea no se vería nunca: sus palabras pasan al principio de la línea siguiente, o al final de la anterior si es la última (decidido por Alex el 26 nov 2026), aunque esa línea pase de 4 palabras o 22 caracteres.
4. **Resaltado y pop:** la palabra actual en blanco #FFFFFF, el resto en #FF7B2A, sobre caja negra (`BorderStyle 3`, 18 px de margen). La línea entra al 80 % y llega al 100 % en 80 ms; a 30 fps se ven 84 %, 92,5 % y 100 % (medido: 431, 477 y 518 px de ancho). Los eventos que empiezan dentro de los 80 ms siguen la misma curva.
5. **Posición:** centrada en x = 540; cada línea, 20 px debajo de la barbilla más baja (borde inferior de la caja de la cara, en píxeles de salida) durante sus fotogramas, sin salir del cuadro. Sin ninguna caja de cara en todo el clip, la caja se apoya en el borde inferior de la zona segura; en un hueco sin cara, `face_at` mantiene la última caja y la línea sigue debajo de ella (cuando llegue `fit_blur` para los tramos sin cara, §5.3, habrá que revisarlo). En el tramo de prueba (primer plano) la barbilla llega a y = 1376–1680 según el fotograma; la más baja de cada línea va de 1483 a 1680, y como el centro de la caja es barbilla + 20 + 108 ÷ 2, los centros quedan entre 1483 + 74 = 1557 y 1680 + 74 = 1754. Los 108 px son la caja calculada (72 + 2 × 18); libass la dibuja de 110 (de centro − 55 a centro + 54, medido en las 27 líneas), así que el espacio medido con la barbilla es 19 px y el borde más bajo, 1809. Caen en la zona de botones: "nunca sobre la cara" (Guidepost) gana sobre "nada tapado por los botones" (reglas base), y `verify-clip` lo avisa sin fallar.
6. **Zona segura orgánica** (aviso): arriba 160, abajo 400, izquierda 65, derecha 192 px sobre 1080x1920. De dónde sale cada uno: abajo, el valor más prudente de las guías orgánicas (400); derecha, la columna de botones de Google Shorts (192); izquierda, el 6 % de Meta Reels (1080 × 0,06 = 64,8 ≈ 65); arriba, la cifra de TikTok que citan las guías de anuncios (160), dentro del rango orgánico de 110–250. No hay números oficiales para publicaciones normales; los oficiales son de anuncios: Google Shorts arriba 288, abajo 672, izquierda 48, derecha 192; Meta Reels 14 % arriba, 35 % abajo y 6 % a los lados; TikTok publica una plantilla descargable. Las guías no oficiales dan abajo 320–400, arriba 110–250 y derecha 120–192.
7. **Color:** el encabezado lleva `YCbCr Matrix: TV.709`. Sin esa línea, el filtro `ass` de FFmpeg 9.0.2 convierte los colores con la matriz BT.601 y en un clip BT.709 el naranja se ve #FF8124 (255, 129, 36, medido sin compresión); con ella, (254, 122, 41).

Se descartaron, mirando fotogramas reales: la caja naranja invertida en la palabra actual (libass dibuja la caja por letra y se comía letras), agrandar la palabra (deforma la caja y mueve las vecinas), ExtraBold 80 en mayúsculas ('ANSWER ENGINE OPTIMIZATION.' pasa de 1080 px), los subtítulos encima de la cara (tapan frente y pelo) y fijos en el tercio inferior dentro de la zona segura (caja en y = 1410–1520: tapaban la barbilla en los 24 grupos de una primera agrupación de prueba).

### 5.5 Dos personas en el mismo plano

No es la prioridad de la Fase 0, pero el diseño lo contempla. Con dos caras en cuadro, se asocia cada hablante de AssemblyAI a una cara: se compara el movimiento de la boca (MediaPipe Face Landmarker) con los tramos en que habla cada hablante, y la ventana sigue al hablante activo. Se valida cuando llegue un video así.

### 5.6 Compose

Un solo comando FFmpeg con `filter_complex`:

- **Video:** intermedio → recorte que cambia en el tiempo con los keyframes de §5.3 → escala a 1080x1920 → subtítulos y hook (ASS) → logo → tarjeta final → intro y outro si existen.
- **Audio:** voz normalizada a `loudness_lufs` (−14 LUFS, dos pasadas) + música en bucle a `volume_db` con *ducking* (baja cuando hay voz) + sfx en los puntos marcados, si están permitidos.
- **Salida:** H.264 High, `yuv420p`, 30 fps, AAC 48 kHz, `+faststart`. Si supera `max_size_mb`, se recodifica a una tasa objetivo.

El recorte variable se hace con comandos de tiempo de FFmpeg (`sendcmd` sobre el filtro `crop`), **validado en la T2.3** (26 nov 2026) con FFmpeg 9.0.2. El plan B (PyAV) no hizo falta: el render reproduce el camino de cámara fotograma por fotograma, así que un temblor solo puede venir del camino, y PyAV dibujaría el mismo. Detalles que el resultado necesita:

- **Un comando por valor que cambia**, medio fotograma antes de su fotograma: `(n − 0,5) ÷ 30` s. `sendcmd` aplica un comando al primer fotograma cuyo tiempo es igual o posterior; el `t_ms` del keyframe está redondeado a milisegundos (fotograma 2 → 67 ms, pero empieza en 66,7 ms) y con él 188 de 1004 fotogramas salían con la ventana del anterior, incluidos los puentes 167, 380 y 803. El archivo de comandos lo arma el dominio (`sendcmd.py`); el adaptador lo escribe en una carpeta temporal y corre FFmpeg desde ella (en Windows el `:` de `C:/` rompe la opción del filtro).
- **`crop=…:exact=1`.** Sin `exact`, en `yuv420p` `crop` redondea `x` e `y` impares hacia abajo y la cámara avanza de a 2 px.
- **La ventana cambia de tamaño** (92 tamaños y 208 cambios en el tramo de prueba) y `scale=1080:1920` se reconfigura con cada tamaño de entrada, así la salida queda fija; `setsar=1` evita que una ventana que no es exactamente 9:16 deje píxeles no cuadrados. Se descartaron sin medir escalar el cuadro entero con un factor variable y recortar fijo (el mismo mecanismo de reconfiguración, con hasta el doble de píxeles por fotograma) y PyAV (más lento y más código).
- **Escala bicubic.** En el tramo de prueba (33,5 s, recortar + escalar + codificar): bilinear 6,0 s, bicubic 6,7 s, lanczos 8,1 s, spline 17,3 s; el detalle conservado (la salida reducida de nuevo y comparada con el recorte) fue 43,8, 45,4, 44,5 y 44,4 dB. Bicubic y lanczos no se distinguen en la cara; bilinear se ve apenas más blando.
- **Codificación provisional:** CRF 18, preset `veryfast` (elegidos sin medir; la T2.7 mide el tiempo por clip). El audio se copia del intermedio hasta la T2.5 (loudness).
- **Subtítulos** (desde la T2.4): con `--captions`, el filtro `ass=filename=captions.ass:fontsdir=fonts` va al final de la cadena, después de `format=yuv420p`, en el mismo comando; así los subtítulos se dibujan a 1080x1920 y no se recortan ni se escalan. El ASS y las fuentes se copian a la carpeta temporal, por el mismo problema del `:` de `C:/`. Tramo de prueba: `compose` tarda 12,4 s con subtítulos (incluye el render chico que confirma la fuente) y 7,5 s sin ellos.

**Versión mínima: FFmpeg 9.** Con el FFmpeg 6.1.1 de Ubuntu 24.04, `crop` se cae (*segmentation fault*) o se cuelga cuando cambia de tamaño a mitad del video; mover la ventana sin cambiar su tamaño sí funciona (medido en el CI el 26 nov 2026). Las versiones 7 y 8 no se probaron: 9 es la más vieja que se vio funcionar, no un límite demostrado. El CI descarga una compilación fija de FFmpeg 9.0.2 con su sha256, y `compose_clip` falla con un mensaje claro si encuentra una versión menor en vez de colgarse. Una prueba de integración (`worker/tests/integration/test_compose_render.py`) renderiza un video sintético de FFmpeg y falla si se quita `exact=1` o si los comandos usan `t_ms`.

### 5.7 Verify

Desde la T2.3 el comando de desarrollo `verify-clip` mide el clip contra su camino de cámara y falla si algo se sale del límite (aprobados el 26 nov 2026). Las mismas comprobaciones pasan a este paso cuando exista:

| Comprobación | Límite | Tramo de prueba |
| --- | --- | --- |
| Tamaño, fps y fotogramas | 1080x1920, 30 fps, uno por keyframe | 1080x1920, 30, 1004 |
| Sincronía | duración de imagen y audio a ≤ 1 fotograma (33,3 ms) | 9,3 ms |
| Cada fotograma en su ventana | 0 fotogramas que se parezcan más a la ventana de un vecino (por más de 0,5 dB) | 0 |
| Parecido con su ventana | ≥ 35 dB en el peor fotograma | 43,9 dB |
| Puentes en su corte | todos en su fotograma | 9/9 |
| Cara dentro | ≤ 5 % de la caja por lado (o la mitad del sobrante si no cabe y se centra), + 1 px de redondeo; lo que sale del cuadro no cuenta | 0 (peor: 5,4 %, cara de 597 px en ventana de 534) |
| Saltos fuera de los cortes | ≤ 20 px por fotograma (600 px/s). También falla el salto de un empuje legítimo (la cara se movió más rápido que la cámara, §5.3): el clip tiene un movimiento brusco y alguien debe verlo (decidido el 26 nov 2026) | 0 (máx. 17 px) |
| Vaivenes | 0 idas y vueltas a → b → a | 0 |

La primera fila son tres comprobaciones (tamaño, fps y fotogramas): 10 en total. Para el parecido, cada fotograma de la salida se reduce al tamaño de su ventana y se compara (PSNR en gris) con el intermedio recortado en su keyframe y en los de sus vecinos.

Con `--captions` (T2.4, aprobadas por Alex el 26 nov 2026) se suman 5, **15 en total**. El estilo (fuente, colores) se lee del propio ASS, no de valores por defecto, y lo esperado sale de la transcripción y del timeline, no del código que escribió los subtítulos. Se miden sobre lo que dibuja libass: FFmpeg dibuja el ASS solo, sobre un cuadro transparente de 1080x1920, y el filtro `bbox` da en cada fotograma la caja de todo lo dibujado (canal alfa) y la de la palabra resaltada (el canal de color donde el resaltado se separa del texto y la caja: azul, umbral (255 + 42) ÷ 2 = 148 para blanco sobre #FF7B2A). Ese render tarda entre 5 y 9 s en el tramo de prueba (4,95 s y 8,8 s en dos corridas del 26 nov 2026). Dos valores los eligió el desarrollador sin compararlos con otros: la tolerancia de 2 % del ancho para contar un cambio de palabra (el pop mueve el resaltado de 3,9 % a 3,7 % del ancho; pasar de "And" a "if" lo mueve a 28,8 %) y los 2 px de margen de la máscara (cubren el borrón del escalado; 0 y 1 px no se probaron).

| Comprobación | Límite | Tramo de prueba |
| --- | --- | --- |
| Fuente | libass usó solo fuentes de la familia del estilo, negritas si el estilo es negrita, y ninguna de reemplazo | Figtree-Bold |
| Palabras | las de las líneas son exactamente las palabras del rango que no son muletillas, en orden; ninguna fuera del clip | 78 de 78 |
| Sincronía | cada palabra se pone blanca a ≤ ½ fotograma (16,7 ms) de su inicio en el clip (mapa de tiempos del timeline); el cambio se detecta en píxeles, relativo a la caja de la línea, para que el pop no cuente: aparece el resaltado, se mueve más del 2 % del ancho, la caja se achica o la caja cambia después de estar quieta. Dos líneas seguidas que dibujan exactamente la misma caja y el mismo resaltado no se distinguen. Sin palabras resaltadas (`highlight.mode none`) pasa | 78 palabras, media 8,7 ms, peor 16,7 ms (4 palabras que empiezan justo entre dos fotogramas: 8550, 11050, 17050 y 24150 ms, que dan x,5 fotogramas) |
| Cara | 0 fotogramas en que la caja de los subtítulos se superponga a la de la cara | 0; lo más cerca, 19 px |
| Zona segura | caja dentro de la zona orgánica (§5.4). **Solo avisa**: no hace fallar `verify-clip` | Aviso: 1002 fotogramas, borde más bajo 1809 px |

Con subtítulos, el parecido de cada fotograma con su ventana deja afuera la caja de subtítulos medida en ese fotograma (más 2 px de margen), porque el intermedio no los tiene: sin eso el peor parecido caía a 20,1 dB y los puentes a 0/9; con la máscara, 43,8 dB y 9/9. `verify-clip` con subtítulos tarda ~52 s en el tramo de prueba (~44 s sin ellos, medidos el mismo día): de los ~8 s de más, ~5 s son el render de libass y el resto, la comparación con máscara. Además:

- `ffprobe`: resolución, fps, códecs, duración dentro del rango, audio presente.
- Decodificación completa sin errores y detección de cuadros congelados.
- Loudness medido (−14 LUFS ± 1).
- Detección de silencios largos que no estén en `keep_pauses`.
- Genera una vista previa liviana (540x960) para revisar en el celular (RNF-07) y una imagen de portada.

---

## 6. Regenerar por aspecto (RF-13) y editar subtítulos (RF-14)

Cada paso guarda su resultado con el hash de sus entradas; una regeneración solo rehace lo que cambia.

| Pedido | Pasos que se rehacen | Tiempo estimado |
| --- | --- | --- |
| Hook (comentario) | decide (solo hook) → timeline si cambia el cold open → overlays → compose → verify | 1–3 min |
| Texto de subtítulos (edición manual, RF-14) | overlays → compose → verify | ~1–2 min |
| Estilo de subtítulos (cambio del spec) | overlays → compose → verify | ~1–2 min |
| Ritmo o cortes (comentario) | decide → timeline → extract → analyze → overlays → compose → verify | 2–4 min |
| Encuadre (comentario) | analyze (con parámetros ajustados) → compose → verify | 1–3 min |
| Todo | todos | 2–4 min |

Todos quedan dentro de "un clip, menos de 5 minutos" (RNF-02). El comentario del operador llega a Claude junto con el JSON anterior, y Claude devuelve el JSON completo corregido. Así cada versión es autosuficiente.

---

## 7. Revisión automática (RF-11)

La agencia ya tiene un checklist antes de enviar (Pass 1 del editor y Pass 2 del CM). La herramienta automatiza lo que se puede medir:

| Ítem del checklist de la agencia | Cómo se verifica | Tipo |
| --- | --- | --- |
| El archivo se reproduce entero, sin cortes ni congelados | Decodificación completa + detección de congelados | auto |
| Exportación igual al spec (ratio, resolución, fps, audio, nombre) | `ffprobe` + loudness | auto |
| Logo con el tamaño y la posición del spec | Lo coloca el render con los valores del spec; se registra en el plan | auto |
| Subtítulos sin errores | El texto sale de la transcripción; los `caption_fixes` se validan; Haiku revisa nombres propios contra el glosario | auto + llm |
| Subtítulos no tapados por los botones de la plataforma | Posición dentro de la zona segura; hoy solo avisa (§5.7) | auto |
| Subtítulos sincronizados | Tiempos tomados de las palabras a través del mapa de tiempos; se mide en píxeles el fotograma en que cada palabra se resalta (≤ ½ fotograma, §5.7) | auto |
| Subtítulos que no tapan la cara | Caja de subtítulos medida en cada fotograma vs caja de la cara (§5.7) | auto |
| Fuentes y colores del cliente | El plan de render solo usa fuentes y colores del spec; `forbidden_fonts` | auto |
| Hook en los primeros 3 s | Validación del JSON | auto |
| Ritmo: sin silencios largos ni planos estáticos largos | Detección de silencios + intervalo entre cambios de encuadre ≤ `max_static_s` | auto |
| Se cumple cada regla del change log | Haiku compara las reglas en texto con el resumen del plan de render | llm |
| No aparece nada de "Never do" | Según `check` de cada regla | auto / llm / manual |
| Verlo en el celular, compararlo con la referencia, "¿lo publicaría hoy?" | El operador en la pantalla de revisión | manual |

El resultado va a `piece_versions.validation` con la lista de problemas. Las reglas `manual` aparecen como una lista de verificación en la tarjeta del clip.

---

## 8. Archivos intermedios

```
work/{job_id}/clips/{piece_id}/
  decision.{hash}.json
  timeline.{hash}.json
  mezzanine.{hash}.mp4
  analysis.{hash}.json          # caras + keyframes de recorte
  captions.{hash}.ass
  overlays.{hash}/              # logo escalado, tarjeta final
pieces/{job_id}/{piece_id}/v{n}/
  clip.mp4
  preview.mp4                   # 540x960
  poster.jpg
```

El archivo de comandos de `sendcmd` no se guarda aquí: lo escribe el adaptador en una carpeta temporal para cada render y sale de los keyframes de `analysis` (§5.6). `work/` se borra con la retención del original (RNF-06). La versión final queda en `pieces/`.

---

## 9. Rendimiento estimado (clip de 60 s, 8 núcleos)

| Paso | Estimado |
| --- | --- |
| decide (Claude) | 15–40 s |
| timeline | < 1 s |
| extract | 10–20 s |
| analyze | 10–20 s |
| overlays | < 5 s |
| compose (incluye loudness en dos pasadas) | 50–100 s |
| verify | 10–15 s |
| **Total** | **~2–3 min por clip**; 6 clips con 3 en paralelo ≈ 5–8 min |

Se mide en la Fase 0. Medido en la T2.3 sobre el tramo de prueba (33,5 s): `compose` solo con recorte, escala y codificación, ~7 s; `verify-clip`, que compara cada fotograma con su ventana, ~24 s, por encima de la fila verify (revisar en la T2.7 si en producción se compara una muestra de fotogramas). Medido en la T2.4 sobre el mismo tramo: armar el ASS (`captions`), menos de 1 s; `compose` con subtítulos, 12,4 s (7,5 s sin ellos, medido el mismo día); `verify-clip` con subtítulos, ~52 s (~44 s sin ellos el mismo día; de los ~8 s de más, ~5 s son el render de libass que mide los subtítulos y el resto, la comparación de fotogramas con máscara). El resto lo mide la T2.7.

---

## 10. Fase 0 (1 semana)

**Objetivo:** demostrar con videos reales que el pipeline propio produce clips aceptables antes de construir la app.

**Material:** una grabación propia del mismo tipo que los videos de Guidepost (una persona a cámara, grabación horizontal, en inglés) y el Edit Spec de Guidepost. La agencia no puede compartir videos de clientes por ahora (`00-resumen-decisiones.md`, "Material de prueba").

**Forma:** comandos de línea de comandos en el worker, sin base de datos ni web (`python -m content_engine <comando>`): hoy uno por paso (`cut`, `detect-faces`, `camera-path`, `captions`, `compose`, `verify-clip`); la T2.7 agrega `prototype`, que los encadena. La transcripción se pide una vez a AssemblyAI y se guarda en un archivo.

| # | Experimento | Criterio de éxito |
| --- | --- | --- |
| 1 | Timeline con muletillas, pausas y J cuts | Ningún corte se come una sílaba; los cortes no se notan al escucharlos |
| 2 | Encuadre 16:9 → 9:16 con MediaPipe | La cara siempre completa; sin temblores; movimiento casi imperceptible en plano fijo |
| 3 | Zooms y puentes de corte con recorte variable (`sendcmd`) | Movimiento fluido; si no, se prueba el plan B (PyAV). **Cumplido en la T2.3 con `sendcmd`** (`verify-clip` 10 de 10, §5.6–5.7) |
| 4 | Subtítulos ASS en Figtree, naranja sobre negro, resaltado por palabra | Sincronía a simple vista; nunca sobre la cara. **Cumplido en la T2.4**: Alex aprobó el video, y medido, 78 palabras a ≤ 16,7 ms y 0 fotogramas sobre la cara (§5.4, §5.7) |
| 5 | Audio a −14 LUFS, sin sfx (Guidepost) | Medido con FFmpeg |
| 6 | JSON de decisiones con Claude sobre 3 momentos reales | JSON válido sin intervención; hook dentro de 3 s; duración en rango |
| 7 | Tiempo por clip | ≤ 3 min en la máquina del desarrollador |

**Entregable:** 3 clips de un mismo video, comparados lado a lado con la muestra aprobada del 5 nov, más un informe corto de tiempos y problemas. Los gráficos explicativos no se esperan (fuera de alcance).

---

## 11. Riesgos

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Clientes como Guidepost dependen de gráficos animados (fuera de alcance) | Para ellos el revisor de video no se podrá apagar y no llegarán a la meta de 90 % de clips sin editor | Avisar a la agencia ahora; medir la meta solo en clientes sin esa regla |
| Recorte variable con `sendcmd` no fluido | Zooms y encuadre bruscos | **Cerrado en la T2.3:** `verify-clip` 10 de 10, 0 de 1004 fotogramas fuera de su ventana; PyAV descartado (§5.6). La prueba de integración avisa si otra versión de FFmpeg rompe el recorte |
| "Cambio visual cada 2–3 s" con una sola cámara se vuelve repetitivo | Clips monótonos | Alternar puentes de corte y zooms; ajustar con la muestra aprobada |
| Edit Specs con muchos campos "[To confirm]" | El resultado no coincide con lo que el cliente espera | Usar reglas base y mostrar los pendientes en la ficha del cliente |
| Nombres de marca mal transcritos | Subtítulos con errores | Glosario del cliente a AssemblyAI + revisión con Haiku |
| Grabación en primer plano: la cara llena el clip vertical | Los subtítulos, debajo de la cara, caen en la zona de botones de TikTok y Reels (tramo de prueba: borde más bajo 1809 px de 1920) | `verify-clip` lo avisa (§5.7). Revisar con el encuadre real de Kyle; si se repite, pedir un plano más abierto en la guía de grabación o decidir otra posición |
| Dos personas o varias cámaras | Encuadre incorrecto | Fuera de la prioridad de la Fase 0; §5.5 para el mismo plano |

---

## 12. Cambios en otros documentos

- `02-modelo-de-datos.md`: tabla `baseline_spec_versions`, columnas `jobs.baseline_version_id` y `jobs.effective_spec`, `corrections.origin` y `corrections.client_quote`, tipo de recurso `sfx`, campo `voice.glossary`, y `edit_spec` con la estructura de §2.2.
- `00-resumen-decisiones.md`: decisiones de §1.
