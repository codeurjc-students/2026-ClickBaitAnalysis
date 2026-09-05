// @ts-check
const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = defineConfig([
  {
    // El cliente tipado lo escribe `openapi-typescript`, no nosotros (#126). Sus
    // 16 avisos de estilo eran los ÚNICOS del proyecto, y arreglarlos sería
    // trabajo perdido: la siguiente regeneración los devuelve. Mismo criterio
    // que `evaluation/` en `.coveragerc` y en `pyrightconfig.json` — lo que no
    // se escribe a mano no entra en la cuenta.
    //
    // `openapi.json` no hace falta excluirlo: ESLint no mira JSON.
    ignores: ['src/app/api/schema.d.ts'],
  },
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      // `recommendedTypeChecked` y no `recommended` a secas: sube el conjunto a
      // las reglas que necesitan el tipo real, no sólo la sintaxis. Se midió
      // antes de adoptarlo, que es la regla de esta casa — **2 problemas** sobre
      // todo el frontend, los dos en el mismo sitio y los dos ciertos.
      tseslint.configs.recommendedTypeChecked,
      tseslint.configs.stylistic,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,

    // Linting CON información de tipos. No es un lujo: sin esto, las reglas que
    // de verdad importan aquí ni siquiera se cargan — `no-uncalled-signals`
    // aborta con «You have used a rule which requires type information».
    //
    // Coste medido: 3,9 s el frontend entero. A cambio entran también las reglas
    // de promesas sin esperar, que en una SPA con `HttpClient` es un fallo real
    // y silencioso.
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: __dirname,
      },
    },
    rules: {
      // La respuesta parcial al fallo más peligroso de este frontend.
      //
      // En zoneless, tratar la señal como si fuera su valor no da error: la
      // pantalla simplemente no dice lo que debería. Esta regla caza una de las
      // dos caras — usar la señal sin llamarla, `this.enviando ? 1 : 0` — y lo
      // dice con su línea. Comprobado provocándolo.
      //
      // La otra cara NO la cubre nadie, y conviene que conste: guardar el estado
      // en un campo normal en vez de en un `signal()` es indistinguible de
      // código correcto para cualquier herramienta. Ese invariante sigue
      // sostenido sólo por convención.
      //
      // No viene en el conjunto recomendado; se activa a mano.
      '@angular-eslint/no-uncalled-signals': 'error',
      '@angular-eslint/directive-selector': [
        'error',
        {
          type: 'attribute',
          prefix: 'app',
          style: 'camelCase',
        },
      ],
      '@angular-eslint/component-selector': [
        'error',
        {
          type: 'element',
          prefix: 'app',
          style: 'kebab-case',
        },
      ],
    },
  },
  {
    // `templateAccessibility` es la mitad valiosa de esto (#140), y viene en la
    // configuración por defecto de angular-eslint. Cubre lo que hasta ahora
    // dependía de que alguien se acordara en cada plantilla: controles sin
    // etiqueta asociada, imágenes sin alternativa textual, y manejadores de
    // ratón sin equivalente de teclado.
    //
    // Comprobado que las reglas están vivas, no sólo declaradas: metiendo un
    // `<img>` sin `alt` y un `(click)` en un `<div>` salen tres errores, entre
    // ellos `interactive-supports-focus`. Las plantillas actuales pasan porque
    // la accesibilidad de #127 se escribió a mano y bien, no porque las reglas
    // sean flojas.
    files: ['**/*.html'],
    extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
    rules: {},
  },
]);
