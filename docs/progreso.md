# Progreso

Registro de tareas cerradas del plan (`07-plan-de-trabajo.md`). Una línea por tarea: fecha, tarea y notas breves si hacen falta. El detalle de cada cambio vive en el historial de git.

- 13 nov 2026 · Documentación 00 a 07 terminada.
- 13 nov 2026 · **T1.1** Instalar las herramientas. Se usa Node.js 26 (LTS) en lugar de 22; Supabase CLI y FFmpeg instalados con Scoop.
- 13 nov 2026 · **T1.2** Crear el repositorio y su estructura. Repo público (no privado) para poder proteger `main` sin plan de pago; código en inglés; scripts de la raíz se agregan en cada tarea que los necesita.
- 15 nov 2026 · **T1.3** Repaso de Python con el proyecto del worker. Pyright en modo estricto; un único `.env` en la raíz leído desde `worker/`; se sube `aeo-content-engine.code-workspace` para VS Code.
- 17 nov 2026 · **T1.4** Transcribir tu grabación de prueba. Comandos `extract-audio` y `transcribe`; muletillas detectadas por el worker y glosario por `keyterms_prompt` (ver decisión en `00`). La grabación usada dura 88 s y no tiene muletillas: **volver a grabar 2–3 min con algún "um" antes de la T1.5**.
- 19 nov 2026 · **T1.5** Timeline: de palabras a cortes. Pausas largas cortadas como muletillas y J cuts fijos de 4 fotogramas en `video_cuts`, con el audio intacto (ver decisiones en `00`).
