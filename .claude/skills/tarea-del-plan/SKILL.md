---
name: tarea-del-plan
description: Ejecuta una tarea del plan de trabajo del Content Engine (T1.1, T2.4, T3.3, T5.6...). Usala siempre que se nombre una tarea "T*.*", se diga "vamos con T1.3", "empecemos la T2.4", "siguiente tarea" o "que toca ahora", o se vaya a construir algo que es una tarea de docs/07. Tambien cuando se pregunte en que quedo el proyecto, o se quiera cerrar una tarea y dejar el progreso anotado.
---

# Ejecutar una tarea del plan

El plan de trabajo (`docs/07-plan-de-trabajo.md`) esta escrito como un tutorial: cada tarea dice que se construye, que se aprende y los pasos en orden, cada uno con su comprobacion (✔). Esta skill es como se recorre.

## 1. Situate antes de empezar

1. Lee la linea de **progreso** en `CLAUDE.md`: dice cual es la tarea siguiente. El registro completo esta en `docs/progreso.md`.
2. Abre `docs/07-plan-de-trabajo.md` y busca la tarea exacta (`### T1.3 · ...`). Trae: **que vas a construir**, **que vas a aprender**, **lee antes**, los **pasos** con su ✔ y **terminaste cuando**.
3. Lee la seccion que indique "**Lee antes**". Es la parte del diseño que esa tarea implementa; sin eso se termina improvisando.
4. Si la tarea toca algo que no esta decidido en los documentos, **pregunta antes de asumir** en lugar de resolverlo por tu cuenta.
5. **Rama:** crea `feat/…` desde `main` actualizado (`git pull --ff-only`). Borra una rama vieja solo si su PR esta fusionado: `test "$(gh pr view <rama> --json state --jq .state)" = MERGED` tiene que dar exito antes del `git branch -D` y del `git push --delete`, en el mismo comando. Si da otro estado, detente y avisa (26 nov 2026: se borro la rama de un PR abierto y GitHub lo cerro).

Las comprobaciones ✔ estan en `docs/07`, no en ClickUp: las subtareas de ClickUp traen el texto del paso pero no el comando que lo verifica.

## 2. Anuncia el alcance

En pocas lineas, antes de tocar nada: **que se va a construir** y para que sirve en el producto (concreto: "con esto el operador ya puede..."), **que se aprende** en la tarea y **cuantos pasos** son.

## 3. Un paso a la vez

Para cada paso del plan:

1. **Que hace** y por que va en ese orden.
2. **Que archivo** se escribe, donde va y que debe contener.
3. **Como comprobar que funciono** (el ✔ del plan): el comando y que deberia aparecer. Si el paso no trae ✔ en el documento, define una comprobacion concreta y verificable.
4. **No sigas al paso siguiente sin la comprobacion en verde.** Si falla, diagnostica antes de cambiar codigo: lee el error, ubica cual de los pasos anteriores lo causa.

## 4. Respeta las reglas del proyecto mientras construyes

Las reglas de `CLAUDE.md` valen tambien dentro de una tarea del plan: no tomes un atajo que rompa el dominio puro, las escrituras por `rpc` o los limites entre modulos. Si el camino corto rompe una regla, dilo y usa el bueno.

Para el detalle que no esta en `CLAUDE.md`: la skill `arquitectura` (flujo, estados, cola, modulos, Edit Spec) y la skill `interfaz` (pantallas y componentes). Al terminar codigo de varios archivos, el agente `revisor-de-codigo` lo revisa contra las reglas.

## 5. Cierra la tarea

Cuando se cumpla el "**terminaste cuando**" del documento:

1. Pasa el agente `documentador` por el codigo nuevo o cambiado en la tarea: es el unico que escribe docstrings.
2. Corre `pnpm lint` y `pnpm test` en la raiz (hoy cubren el worker); el CI repite lo mismo en el PR y no deja fusionar si falla.
3. Pasa el agente `explicador` por el codigo de la tarea (dale el rango `main...HEAD`, no tu explicacion: es independiente). Si devuelve una pagina, publicala como artifact. Muestra a Alex sus diferencias con `docs/` y sus preguntas de comprobacion antes de abrir el PR.
4. Marca la tarea y sus subtareas como hechas en ClickUp (space **Content Engine**, carpeta **Fase 0 y Fase 1**, listas S1 a S6).
5. **Anota el progreso**: agrega una linea a `docs/progreso.md` (fecha, tarea terminada y una nota breve si hace falta) y reemplaza la linea de **Progreso** en `CLAUDE.md` con la ultima tarea cerrada y la siguiente. Una linea, no un informe.
6. Si en la tarea aparecio una decision nueva o algo que contradice un documento, propon actualizar `docs/` y `docs/00-resumen-decisiones.md`. El agente `guardian-de-docs` sirve para esa revision.
7. Registra los aprendizajes de la tarea (los que propusieron los agentes y los que surgieron en la conversacion) con la skill `registrar-aprendizaje`.

## Si lo que se pide no es una tarea del plan

Puede pertenecer a una fase todavia sin planificar: solo estan escritas la Fase 0 y la Fase 1. Dilo, y ofrece dos caminos: planificarla primero con el formato de `docs/07`, o hacerla como trabajo suelto sabiendo que queda fuera del plan.

## Como acompañar

Si el entorno local aporta reglas sobre el trato (cuanto codigo entregar, como explicar, en que idioma, a que ritmo), tienen prioridad sobre el tono de esta skill.
