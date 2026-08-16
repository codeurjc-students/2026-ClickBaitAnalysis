"""Lógica del dominio del clickbait, independiente de cómo se sirva.

**Criterio de pertenencia**: si borraras la API REST y el servidor MCP y dejaras
sólo una función de Python que analiza titulares, ¿esto seguiría haciendo falta?
Si la respuesta es **sí**, va aquí.

Existe porque la orquestación —contrastar las señales, agruparlas por dimensión y
derivar el veredicto— vivía en ``backend/api/analyze.py``, donde no le
correspondía: estaba ahí porque era donde hizo falta primero. La consecuencia era
concreta y no estética: el servidor MCP no exponía ninguna herramienta que
contrastara señales, así que un agente conversacional **no podía reproducir el
veredicto del formulario** — obtenía las señales sueltas y tenía que combinarlas
él, que es exactamente el veredicto de caja negra que este proyecto rechaza.

Ninguna carpeta existente lo admitía, y sus propios criterios lo dicen:

- ``api/`` — ¿existiría sin HTTP? Sí. Fuera.
- ``core/`` — ¿ignora el dominio del clickbait? No, lo sabe todo. Fuera.
- ``integrations/`` — ¿envuelve algo externo? No envuelve nada. Fuera.

**La regla que mantiene esto honesto**: ``api/schemas.py`` puede importar de aquí;
**nunca al revés**. El dominio no sabe que lo están sirviendo. Y es comprobable:
el día que este paquete necesite importar de ``api/``, algo está mal colocado.
"""
