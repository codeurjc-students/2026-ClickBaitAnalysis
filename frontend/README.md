# clickbait-web

La interfaz web del sistema: una SPA de Angular que habla con la API REST por
`/api`. La generó Angular CLI 22.1.6, y la guía que traía se sustituyó por la
del proyecto (#251).

- **Cómo se prepara, se arranca y se comprueba**:
  [`docs/desarrollo.md`](../docs/desarrollo.md).
- **Cómo está organizada**: las capas y de dónde salen los tipos, en
  [§8 de `docs/arquitectura.md`](../docs/arquitectura.md#8--el-frontend-sus-capas-y-de-dónde-salen-sus-tipos);
  qué va en cada carpeta, en [`docs/estructura.md`](../docs/estructura.md).

Lo esencial, desde esta carpeta y con la API escuchando en el 8000:

```bash
npm ci
npm start
```

Se abre en `http://localhost:4200`, y `proxy.conf.json` reenvía `/api` a la API.
