# Notas de referencias visuales

De estas imágenes se toma **la forma** (distribución, tamaños, bordes, comportamiento), no los colores. Los colores salen de `style-example.txt` (tema de tweakcn).

---

## sidebar.png

**Qué se toma:**

- **Sidebar flotante:** separado del borde de la pantalla, con esquinas redondeadas (~16 px) y sombra suave.
- **Logo arriba**, ícono dentro de un cuadrado redondeado + nombre.
- **Ítems:** ícono a la izquierda + texto; alto ~36–40 px; buen espacio vertical entre ítems.
- **Ítem activo:** "píldora" rellena con el color principal; el ícono va en un cuadrado redondeado que resalta. Texto en blanco y negrita.
- **Grupos:** ítems relacionados dentro de un panel con fondo apenas más claro que el sidebar y esquinas redondeadas (en la imagen: Swap, Add Liquidity, Manage Liquidity…).
- **Colapsable:** se reduce a una barra solo de íconos; al pasar el mouse aparece un tooltip con el nombre. El botón "Collapse Sidebar" va abajo.
- **Íconos de trazo fino** (~1.5), de línea, sin relleno.
- **Estados:** normal (texto gris), hover (fondo suave), activo (relleno de color).

**Qué no se toma:**

- Los íconos de redes sociales del pie (no aplican).
- Dos colores de activo a la vez (verde y celeste): en la app habrá **un solo color de activo**, el principal.
- El tamaño de letra muy chico (~11 px): en la app, mínimo 14 px.

**Uso en la app:** menú principal. Grupos posibles: Trabajo (Nuevo video, Revisión), Clientes, Admin (Usuarios, Reglas base, Métricas).

---

## forms.png

**Qué se toma:**

- **Card del formulario:** fondo blanco sobre un fondo gris muy claro, esquinas grandes (~16–20 px), sin sombra marcada, mucho espacio interno (~32 px).
- **Título** grande en semibold + subtítulo corto debajo.
- **Etiqueta arriba de cada campo**, en color de texto principal, tamaño normal (no gris pequeño).
- **Campos:** alto ~44 px, borde gris de 1 px visible, esquinas ~6 px, texto de ayuda (placeholder) gris claro.
- **Campos cortos en dos o tres columnas** (nombre y apellido; mes, día y año).
- **Bloque de información de solo lectura:** fondo gris claro relleno, sin borde, esquinas redondeadas.
- **Botón principal ancho completo** al final, alto ~48 px.
- Separación vertical generosa entre campos (~20–24 px).

**Qué no se toma:**

- El color gris violáceo del botón: el botón usa el color principal de la paleta.

**Uso en la app:** login, crear cliente, perfil y Edit Spec, nuevo trabajo, crear usuario.

---

## style-example.txt (tema de tweakcn)

**Colores en hexadecimal:**

| Uso | Claro | Oscuro |
| --- | --- | --- |
| Fondo | `#F8FAFC` | `#060B19` |
| Texto | `#0F172A` | `#FFFFFF` |
| Card | `#FFFFFF` | `#0F172A` |
| Principal (índigo) | `#4F46E5` | `#6366F1` |
| Secundario (verde azulado) | `#00C49F` | `#00C49F` |
| Fondo apagado | `#F1F5F9` | `#1E293B` |
| Texto secundario | `#475569` | `#94A3B8` |
| Borde | `#E2E8F0` | `#1E293B` |
| Error | `#EF4444` | `#7F1D1D` |

**Se reemplaza del archivo:** las fuentes (`Inter`, `Merriweather`, `Fira Code`) por **Manrope** y una monoespaciada para tiempos.

**Ajustes de contraste** (para que el texto se lea bien; mínimo recomendado 4.5 a 1):

| Combinación | Contraste | Ajuste |
| --- | --- | --- |
| Texto blanco sobre el verde azulado `#00C49F` | 2.2 | Texto oscuro `#0F172A` sobre el verde (8.0), como ya hace el modo oscuro |
| Texto blanco sobre el rojo `#EF4444` | 3.8 | Rojo más oscuro `#DC2626` para botones de borrar |
| Texto blanco sobre índigo oscuro `#6366F1` | 4.5 (justo) | Texto en semibold, o índigo un poco más oscuro |
| Borde de campos `#E2E8F0` sobre blanco | 1.2 | Borde de campos más visible (~`#94A3B8`), como en `forms.png`; las cards pueden seguir con el borde suave |
