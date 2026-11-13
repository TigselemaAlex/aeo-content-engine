#!/usr/bin/env node
// Revisa las reglas de arquitectura del Content Engine (ver CLAUDE.md).
//
//   node .claude/hooks/check-reglas.mjs pre    -> PreToolUse  (puede pedir confirmacion)
//   node .claude/hooks/check-reglas.mjs post   -> PostToolUse (avisa a Claude con exit 2)
//
// Recibe el JSON del hook por stdin. Los mensajes van sin acentos a proposito,
// para que no se rompan en la consola de Windows.

import { readFileSync, existsSync } from 'node:fs';

const modo = process.argv[2] ?? 'post';

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, 'utf8'));
} catch {
  process.exit(0); // sin JSON valido no hay nada que revisar
}

const archivo = entrada?.tool_input?.file_path ?? entrada?.tool_response?.filePath ?? '';
if (!archivo) process.exit(0);

const ruta = archivo.replace(/\\/g, '/');

// --- PreToolUse: una migracion ya aplicada no se edita -----------------------

if (modo === 'pre') {
  if (entrada.tool_name === 'Edit' && /\/supabase\/migrations\/[^/]+\.sql$/.test(ruta)) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'ask',
        permissionDecisionReason:
          'Regla del proyecto: nunca se edita una migracion ya aplicada; cada cambio de esquema ' +
          'es una migracion nueva en supabase/migrations/. Confirma solo si esta migracion no se ' +
          'aplico todavia en ninguna base.',
      },
    }));
  }
  process.exit(0);
}

// --- PostToolUse: reglas sobre el archivo que se acaba de escribir ----------

if (!existsSync(archivo)) process.exit(0);

let texto;
try {
  texto = readFileSync(archivo, 'utf8');
} catch {
  process.exit(0);
}

const problemas = [];
const anota = (regla, detalle) => problemas.push(`[${regla}] ${detalle}`);

const esPython = ruta.endsWith('.py');
const esWeb = ruta.includes('/apps/web/');
const esTsx = /\.tsx?$/.test(ruta);

// 1. El dominio es puro: nada de red, disco, base de datos ni subprocess.
if (esPython && /\/domain\//.test(ruta)) {
  for (const mod of ['psycopg', 'anthropic', 'assemblyai', 'boto3', 'mediapipe',
                     'playwright', 'subprocess', 'requests', 'httpx']) {
    if (new RegExp(`^\\s*(?:import\\s+${mod}|from\\s+${mod}[\\s.])`, 'm').test(texto)) {
      anota('dominio puro', `${mod} no se importa dentro de */domain/. Esa llamada va en ` +
        'adapters/, y el dominio la usa a traves de un puerto de ports/.');
    }
  }
}

// 2. Un paso habla por puertos, nunca directo con un adaptador.
if (esPython && /\/steps\//.test(ruta) && /^\s*(?:from|import)\s+\S*adapters/m.test(texto)) {
  anota('capas del worker', 'un paso de steps/ no importa adapters: recibe los adaptadores ' +
    'ya armados en StepContext (storage, llm, transcriber...).');
}

// 3. Todo lo de modules/*/server/ empieza con import 'server-only'.
if (esTsx && /\/apps\/web\/src\/modules\/[^/]+\/server\//.test(ruta)) {
  const primera = texto.split('\n').map((l) => l.trim())
    .find((l) => l !== '' && !l.startsWith('//')) ?? '';
  if (!/^import\s+['"]server-only['"]/.test(primera)) {
    anota('server-only', "este archivo esta en modules/*/server/ y debe empezar con " +
      "import 'server-only'; asi el build falla si lo importa un componente de cliente.");
  }
}

// 4. Iconos de Tabler, no Lucide.
if (esWeb && /lucide-react/.test(texto)) {
  anota('iconos', 'el proyecto usa Tabler (@tabler/icons-react, trazo 1.5). Cambia el icono de ' +
    'Lucide por el equivalente de Tabler, tambien en los componentes de shadcn.');
}

// 5. La clave service_role solo sirve para crear cuentas.
if (esWeb && /SERVICE_ROLE/.test(texto)
    && !/\/modules\/auth\/server\//.test(ruta) && !/\/app\/api\//.test(ruta)) {
  anota('service_role', 'la clave service_role se salta los permisos por fila y en la web solo ' +
    'se usa para crear cuentas (modules/auth/server/ o un Route Handler de admin). Las demas ' +
    'escrituras van por una rpc con la sesion del usuario.');
}

// 6. app/ solo compone paginas: no entra a las carpetas internas de un modulo.
if (esTsx && /\/apps\/web\/src\/app\//.test(ruta)) {
  const malImport = texto.match(/from\s+['"]@\/modules\/[^/'"]+\/(?!index['"])[^'"]+['"]/);
  if (malImport) {
    anota('limites de modulo', `app/ importa ${malImport[0]}. Debe pedirlo a la API publica del ` +
      'modulo (@/modules/<nombre>), no a sus carpetas internas.');
  }
}

// 7. Cada prompt lleva su encabezado de version.
if (/\/worker\/prompts\/.+\.j2$/.test(ruta)
    && !/version/i.test(texto.split('\n').slice(0, 12).join('\n'))) {
  anota('prompts', 'cada prompt de worker/prompts/ lleva un encabezado con su version. Al ' +
    'cambiar el prompt, sube la version y corre worker/evals.');
}

if (problemas.length > 0) {
  process.stderr.write(
    `Reglas del Content Engine sin cumplir en ${ruta}:\n\n` +
    problemas.map((p) => `- ${p}`).join('\n') +
    '\n\nCorrige esto antes de seguir (detalle en CLAUDE.md).\n',
  );
  process.exit(2);
}
