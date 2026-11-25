---
name: registrar-aprendizaje
description: Convierte lo que se aprendio trabajando (un error que se repite, una regla que faltaba, un valor que se descubrio probando, un atajo que rompio algo) en una barrera automatica, una regla o una skill, sin contradecir lo ya escrito. Usala cuando un agente devuelva una seccion "Aprendizajes", cuando Alex corrija como se hizo algo, cuando se arregle un error que podria repetirse y al cerrar una tarea del plan. Primero busca si ya existe o choca con algo; si es compatible lo agrega, si se superpone lo fusiona y si se contradice y no se puede unir, pregunta a Alex.
---

# Registrar un aprendizaje

Un aprendizaje que solo queda en la conversacion se pierde. Uno que se escribe sin revisar termina en reglas repetidas o contradictorias. Esta skill es el camino del medio: **cada aprendizaje termina en un solo lugar, sin chocar con lo que ya existe**.

Solo la sesion principal la ejecuta. Los agentes (`documentador`, `revisor-de-codigo`, `guardian-de-docs`) **proponen** aprendizajes en su informe y no los escriben: corren aparte, no pueden preguntarle a Alex y, si trabajan en paralelo, se pisarian al escribir el mismo archivo.

## 1. Decide si vale la pena guardarlo

Se guarda si **volveria a pasar** en otra tarea o en otra sesion. No se guarda:

- lo que ya dicen el codigo, sus docstrings o el historial de git;
- un detalle que solo importa en esta tarea;
- algo que ya esta escrito igual en otro lugar (en ese caso, a lo sumo se aclara el texto existente).

## 2. Elige el lugar: de lo que no gasta tokens a lo que si

Usa el **primer** lugar que sirva. Una regla en codigo corre siempre, no gasta tokens y no se puede ignorar; una regla en texto se paga en cada sesion y se puede olvidar.

| Si el aprendizaje es… | Va en | Ejemplo |
| --- | --- | --- |
| Comprobable con codigo | Barrera: regla de Ruff, contrato de import-linter (`worker/pyproject.toml`), prueba, hook (`.claude/hooks/check-reglas.mjs`) o paso del CI (`.github/workflows/ci.yml`) | "El dominio importo `cv2`" -> contrato `forbidden` |
| Una decision del producto o de arquitectura | Su documento de `docs/` **y** `docs/00-resumen-decisiones.md` (con fecha y motivo) | "La zona muerta vertical usa el alto de la ventana" |
| Como hacer un tipo de tarea | La skill que ya cubre ese tema (`arquitectura`, `interfaz`, `tarea-del-plan`); una skill nueva solo si ninguna lo cubre | "Para medir un video, contar fotogramas con ffprobe -count_frames" |
| Como debe trabajar un agente | Ese archivo en `.claude/agents/` | "El documentador comprueba el `--help` de los comandos de Typer" |
| Una regla dura que toda sesion necesita | `CLAUDE.md`, en una linea (es caro: se carga siempre) | Rara vez |
| Como trabaja Alex (personal) | `.claude/rules/forma-de-trabajo.md` (local, no se versiona) | "Explicar las formulas con graficos" |

Lo que va al repositorio pasa a la agencia (RNF-09): nada personal fuera de `.claude/rules/`.

## 3. Busca si ya existe o si choca con algo

Antes de escribir, busca con Grep las palabras clave del aprendizaje (y sus sinonimos, en español y en ingles) en:

`CLAUDE.md`, `.claude/agents/`, `.claude/skills/`, `.claude/rules/`, `.claude/hooks/`, `docs/00-resumen-decisiones.md`, el documento de `docs/` del tema y, si es una barrera, `worker/pyproject.toml` y `.github/workflows/`.

Lee solo los fragmentos que aparecen, no los archivos enteros. Despues clasifica:

| Resultado | Que haces |
| --- | --- |
| **No hay nada parecido** | Lo agregas en el lugar elegido. |
| **Ya esta dicho igual** | No agregas nada. Si el texto existente era confuso, lo aclaras. |
| **Se superpone** (dicen cosas compatibles en dos lugares) | **Fusionas**: una sola regla en el lugar correcto, y en el otro lugar, si hace falta, solo una referencia (`ver docs/03 §5.3`). Nunca dos copias que puedan separarse. |
| **Se contradice y una es claramente vieja** (una decision posterior de `docs/00`, con fecha, ya la cambio) | Actualizas el texto viejo para que diga lo nuevo, y lo cuentas en el informe. |
| **Se contradice y no sabes cual vale** | **No escribas.** Pregunta a Alex con AskUserQuestion: muestra los dos textos con su archivo, explica el choque en una frase y ofrece opciones (quedarse con uno, con el otro, una version que una ambos). Despues aplicas lo que elija. |

Una regla nueva nunca contradice una decision de `docs/00` en silencio: o la decision cambia (y se registra con fecha y motivo) o la regla no entra.

## 4. Escribe corto y con su origen

- Una regla = una o dos lineas, en el idioma del archivo (codigo y configuracion en ingles; `docs/` y `.claude/` en español).
- Di de donde sale: la fecha y que lo provoco ("25 nov 2026: el dominio importo cv2").
- Si es una barrera, **comprueba que atrapa el caso**: provoca la falla a proposito, mira que falle y deshaz el cambio (como se hizo con import-linter y con `D103` de Ruff).

## 5. Informa en una linea por aprendizaje

`<aprendizaje> -> <archivo> (agregado | fusionado con … | actualizado | descartado: ya existia | pendiente: pregunta a Alex)`
