"""Vuelca el contrato OpenAPI de la API REST a ``frontend/openapi.json``.

    python -m backend.api.export_openapi

De ese fichero se genera el cliente TypeScript del frontend (``npm run gen:api``),
de modo que la forma de las respuestas se declara UNA vez —en los modelos Pydantic
de ``backend/analysis/domain.py`` y ``backend/api/schemas.py``— y el resto se
deriva. Escribir las interfaces a mano en el frontend crearía una segunda
definición de la misma verdad, y esa copia no falla al desincronizarse: compila
igual y el dato llega ``undefined`` al navegador.

**Se importa la app en vez de pedirle ``/openapi.json`` a un servidor.** Es lo que
documenta FastAPI para este caso y evita el rodeo entero: no hay que arrancar
uvicorn, ni elegir un puerto libre, ni esperar a que levante, ni matarlo después.
Importar el módulo cuesta ~3 s y no carga ningún modelo NLP —eso ocurre en el
``lifespan``, que aquí no llega a correr—, así que también vale en el CI, que
instala sólo ``requirements.txt`` (sin torch).

El JSON resultante **se commitea**. Así el ``git diff`` de una pull request enseña
qué cambió del contrato; generándolo en el build, ese cambio sería invisible en la
revisión. Que la copia commiteada siga al día lo vigila
``test_el_contrato_commiteado_esta_al_dia``.
"""

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from backend.api.app import app
from backend.integrations.nlp.outputs import (
    Etiqueta,
    SalidaIncoherencia,
    SalidaLexica,
    SalidaLineal,
)

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "frontend" / "openapi.json"

# Las formas conocidas del `data` de cada señal (#133).
#
# `SignalResult.data` es un diccionario libre A PROPÓSITO, para no perder
# información y para que quepan señales que todavía no existen. El precio lo paga
# quien lo consume, y lo estaba pagando DOS veces: estos `TypedDict` aquí, y
# cuatro interfaces escritas a mano en `frontend/analisis/datos.ts`. Las mismas
# formas, dos lenguajes, ningún vínculo — y ninguno de los dos guardianes del CI
# veía esa duplicación.
#
# Publicarlas como esquemas con nombre deja que `openapi-typescript` las genere y
# que el frontend las IMPORTE. Los guardianes de forma se quedan —`data` sigue sin
# tipo en la frontera y hay que comprobar en ejecución— pero pasan a validar
# contra tipos generados en vez de contra copias.
#
# Lo que NO se hace, y es deliberado: tipar `SignalResult.data` como unión de
# estas cuatro. Daría seguridad de tipos, pero el dominio pasaría a conocer cada
# señal concreta y rompería el principio 1 de `domain.py` — hoy añadir una señal
# no toca el dominio, y ésa es la propiedad que más costaría recuperar.
FORMAS_DEL_DATA = (Etiqueta, SalidaLexica, SalidaLineal, SalidaIncoherencia)

# Dónde viven los esquemas en un documento OpenAPI. Pydantic apunta por defecto a
# `#/$defs/...`, que es correcto en JSON Schema suelto y NO resuelve aquí.
PLANTILLA_REF = "#/components/schemas/{model}"


def _publicar_formas_del_data(contrato: dict[str, Any]) -> None:
    """Añade las formas del ``data`` a ``components/schemas``, con los anidados.

    El detalle que hay que tener en cuenta: ``SalidaLexica`` contiene ``Pista``, y
    Pydantic mete los tipos anidados en un ``$defs`` **local al esquema**. Si se
    copiaran tal cual, el documento quedaría con un ``$ref`` colgando y el tipo
    generado saldría como ``unknown``: silencioso, y del tipo exacto de fallo que
    el contrato generado existe para evitar.

    Se resuelve por los dos lados —``ref_template`` para que las referencias
    apunten ya a ``components/schemas``, y subir los anidados ahí— en vez de
    reescribiendo cadenas después.
    """
    destino = contrato["components"]["schemas"]

    for tipo in FORMAS_DEL_DATA:
        esquema = TypeAdapter(tipo).json_schema(ref_template=PLANTILLA_REF)

        for nombre, anidado in esquema.pop("$defs", {}).items():
            # Un choque de nombres sobrescribiría un esquema del contrato en
            # silencio. Es improbable y por eso mismo conviene que grite.
            if nombre in destino and destino[nombre] != anidado:
                raise ValueError(
                    f"El tipo anidado «{nombre}» choca con un esquema que ya "
                    f"existe en el contrato. Renombra uno de los dos."
                )
            destino[nombre] = anidado

        destino[tipo.__name__] = esquema


def contrato() -> str:
    """El texto exacto que debe estar en ``DESTINO``.

    Es una función y no está dentro de ``main`` porque el test compara contra
    ella: si el formato viviera sólo en el volcado, el test tendría que repetirlo
    y cambiar el ``indent`` rompería la comparación sin que nada estuviera mal.

    ``ensure_ascii=False`` porque las descripciones salen de docstrings en
    español: con escapes tipo ``\\u00f3`` el diff de una tilde sería ilegible.
    """
    # Copia, y no es paranoia: `app.openapi()` CACHEA su resultado en
    # `app.openapi_schema` y devuelve siempre el mismo objeto. Enriquecerlo en
    # sitio metería las formas del `data` en el `/openapi.json` que sirve la app
    # a partir de la primera llamada a esta función — o sea, un documento que
    # cambia según si el exportador ha corrido antes, y en la suite eso depende
    # del orden de los tests. Con la copia, esta función es pura.
    documento = copy.deepcopy(app.openapi())
    _publicar_formas_del_data(documento)
    return json.dumps(documento, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    texto = contrato()
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"{DESTINO.relative_to(RAIZ)} · {len(texto)} bytes")


if __name__ == "__main__":
    main()
