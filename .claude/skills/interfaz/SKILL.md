---
name: interfaz
description: Guia visual de la app web del Content Engine (colores, tipografia Manrope, iconos de Tabler, formas de sidebar y formularios, accesibilidad). Usala antes de crear o cambiar cualquier pantalla, componente, layout o estilo en apps/web, al montar shadcn/ui o Tailwind, y cuando haya que decidir un color, un icono, un espaciado o el aspecto de un formulario.
---

# Interfaz del Content Engine

Antes de escribir una pantalla, **lee `design/references/notas.md`** y mira las imagenes de `design/references/` (`sidebar.png`, `forms.png`). De las imagenes se toma la **forma** (distribucion, tamaños, bordes, comportamiento), **nunca sus colores**.

## Reglas que no se negocian

- **Solo modo claro.** El modo oscuro no esta en el alcance del MVP.
- **Colores solo desde el tema.** Nunca un color suelto en un componente. La paleta sale de `design/references/style-example.txt` (tema de tweakcn) con los ajustes de contraste de `notas.md`.
- **Tipografia Manrope.** Reemplaza las fuentes del tema (Inter, Merriweather, Fira Code). La monoespaciada se usa **solo** para tiempos de video y datos.
- **Iconos de Tabler** (`@tabler/icons-react`), trazo 1.5, de linea, sin relleno. **No uses Lucide**: si un componente de shadcn/ui lo trae, cambialo por el equivalente de Tabler. (Un hook del proyecto avisa si entra `lucide-react`.)
- **Textos de la interfaz en ingles** (RNF-07), centralizados por modulo.
- **Nada de aspecto generico:** sin degradados decorativos, sin emojis como iconos, sin sombras fuertes.

## Paleta (modo claro)

| Uso | Color |
| --- | --- |
| Fondo | `#F8FAFC` |
| Card | `#FFFFFF` |
| Texto | `#0F172A` |
| Texto secundario | `#475569` |
| Principal (indigo) | `#4F46E5` |
| Secundario (verde azulado) | `#00C49F` |
| Fondo apagado | `#F1F5F9` |
| Borde | `#E2E8F0` |
| Error | `#EF4444` |

**Ajustes de contraste obligatorios** (minimo 4.5:1), tal como los fija `notas.md`:

- Sobre el verde azulado `#00C49F` el texto va **oscuro** (`#0F172A`), nunca blanco.
- Para botones de borrar, rojo mas oscuro: `#DC2626`.
- El borde de los **campos de formulario** debe ser mas visible que el del tema (~`#94A3B8`); las cards si pueden llevar el borde suave.
- Tamaño de letra minimo 14 px.

## Formas que ya estan decididas

**Sidebar** (menu principal; grupos posibles: Trabajo — Nuevo video, Revision; Clientes; Admin — Usuarios, Reglas base, Metricas):

- Flotante: separado del borde, esquinas ~16 px, sombra suave.
- Logo arriba: icono en un cuadrado redondeado + nombre.
- Items: icono a la izquierda + texto, alto ~36–40 px, buen aire vertical.
- Item activo: pildora rellena con el color principal, icono en cuadrado redondeado, texto blanco en negrita. **Un solo color de activo.**
- Grupos de items dentro de un panel con fondo apenas mas claro, esquinas redondeadas.
- Colapsable a solo iconos con tooltip al pasar el mouse; boton "Collapse Sidebar" abajo.

**Formularios** (login, crear cliente, perfil y Edit Spec, nuevo trabajo, crear usuario):

- Card blanca sobre fondo gris muy claro, esquinas ~16–20 px, sin sombra marcada, ~32 px de aire interno.
- Titulo grande en semibold + subtitulo corto debajo.
- Etiqueta **arriba** de cada campo, en color de texto principal y tamaño normal (no gris pequeño).
- Campos: alto ~44 px, borde 1 px visible, esquinas ~6 px, placeholder gris claro.
- Campos cortos en dos o tres columnas.
- Bloques de solo lectura: fondo gris claro relleno, sin borde, esquinas redondeadas.
- Separacion vertical entre campos ~20–24 px.
- Boton principal de ancho completo al final, alto ~48 px, con el color principal.

## Donde va el codigo

- `apps/web/src/components/ui/` : componentes de shadcn/ui (generados, editables).
- `apps/web/src/modules/<modulo>/ui/` : componentes del modulo (`PieceCard`, `CommentBox`, `ApproveButton`).
- `apps/web/src/app/` : **solo** compone paginas. No importa carpetas internas de modulos.

Los componentes de cliente pueden usar `x/domain`, las Server Actions de `x/server/actions`, `components/ui`, `lib/query` y `lib/supabase/browser`; **no** `x/server/queries` ni las internas de otro modulo.

## Datos en pantalla

La carga inicial la hace un Server Component que llama a `queries.ts` del modulo y pasa los datos como `initialData` a `useQuery`; un hook del modulo (`useJobRealtime(jobId)`) se suscribe a Supabase Realtime y actualiza o invalida la consulta cuando cambian `jobs`, `pieces` o `piece_versions`. Asi la pantalla de revision se actualiza sola, sin recargar.

Solo se prueban con Vitest los componentes de logica no trivial (tarjeta de pieza, editor de subtitulos). La UI se prueba poco; lo que mas vale son las pruebas de dominio del worker y de RLS.
