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

import json
from pathlib import Path

from backend.api.app import app

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "frontend" / "openapi.json"


def contrato() -> str:
    """El texto exacto que debe estar en ``DESTINO``.

    Es una función y no está dentro de ``main`` porque el test compara contra
    ella: si el formato viviera sólo en el volcado, el test tendría que repetirlo
    y cambiar el ``indent`` rompería la comparación sin que nada estuviera mal.

    ``ensure_ascii=False`` porque las descripciones salen de docstrings en
    español: con escapes tipo ``\\u00f3`` el diff de una tilde sería ilegible.
    """
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    texto = contrato()
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"{DESTINO.relative_to(RAIZ)} · {len(texto)} bytes")


if __name__ == "__main__":
    main()
