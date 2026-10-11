"""#235 (2026-10-09) - GNews y NewsData.io por dentro, antes de escribir sus clientes.

Las dos APIs que traerán noticias en español. Antes de escribir un cliente se
mide, contra la API real y con las claves del `.env`, lo que la documentación
no deja claro o lo que hace falta para decidir:

- qué devuelve un tema en español, y qué devuelve sin tema;
- qué campos trae cada artículo, y en qué idioma y de qué medios;
- hasta cuándo llega lo que devuelve (el archivo de cada plan gratuito);
- qué cabeceras dicen algo de la cuota;
- qué responde una clave que no existe, y si esa respuesta repite la clave;
- qué traen `description` y `content` en el plan gratuito (lo que alimentaría
  la incoherencia), y cómo viene la zona horaria de la fecha.

Y aparte, la parte `busqueda`: si lo que devuelve NewsData.io para un tema es
de ese tema, con tres formas de pedirlo (ver `busqueda`).

Ninguna clave se imprime: todo lo que se enseña pasa por `tapar`, que cambia
cada clave por asteriscos aunque una API la repitiera en un error. `todo` gasta
unas cuatro peticiones de cada API (GNews: 100 al día; NewsData.io: 200
créditos), y `busqueda`, seis créditos de NewsData.io.

Ejecutar desde la raíz: .venv/bin/python spikes/noticias_es.py [todo|busqueda]
"""

import sys
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
CLAVES = dotenv_values(RAIZ / ".env")
GNEWS = CLAVES.get("GNEWS_API_KEY") or ""
NEWSDATA = CLAVES.get("NEWSDATA_API_KEY") or ""
CLAVE_FALSA = "claveinventada0000000000000000"
TEMA = "inteligencia artificial"
PAUSA_GNEWS = 1.2  # el plan gratuito admite una petición por segundo


def tapar(texto: str) -> str:
    for clave in (GNEWS, NEWSDATA):
        if clave:
            texto = texto.replace(clave, "***")
    return texto


def cabeceras_de_cuota(respuesta: httpx.Response) -> dict[str, str]:
    return {
        nombre: valor
        for nombre, valor in respuesta.headers.items()
        if any(
            palabra in nombre.lower()
            for palabra in ("limit", "quota", "remaining", "credit", "retry")
        )
    }


def pedir(url: str, parametros: dict) -> httpx.Response:
    respuesta = httpx.get(url, params=parametros, timeout=15)
    print(
        f"  HTTP {respuesta.status_code} · cuota en cabeceras: {cabeceras_de_cuota(respuesta) or 'ninguna'}"
    )
    return respuesta


def resumir(articulos: list[dict], titulo, fecha, medio, idioma) -> None:
    print(
        f"  {len(articulos)} artículos; campos del primero: {sorted(articulos[0]) if articulos else '—'}"
    )
    fechas = sorted(fecha(articulo) for articulo in articulos if fecha(articulo))
    if fechas:
        print(f"  del {fechas[0]} al {fechas[-1]}")
    print(f"  idiomas: {sorted({str(idioma(articulo)) for articulo in articulos})}")
    print(f"  medios: {sorted({str(medio(articulo)) for articulo in articulos})}")
    for nombre in ("description", "content", "pubDateTZ"):
        valores = [articulo.get(nombre) for articulo in articulos if nombre in articulo]
        if not valores:
            continue
        longitudes = sorted(len(str(valor)) for valor in valores if valor)
        vacios = sum(1 for valor in valores if not valor)
        muestra = tapar(str(next((valor for valor in valores if valor), "")))[:70]
        print(
            f"  {nombre}: {vacios} vacíos de {len(valores)}; "
            f"longitud {longitudes[0] if longitudes else 0}–{longitudes[-1] if longitudes else 0}; "
            f"distintos {len({str(valor) for valor in valores})}; ej. «{muestra}»"
        )
    for articulo in articulos[:3]:
        print(f"    · {tapar(str(titulo(articulo)))[:90]}")


def error(respuesta: httpx.Response, clave_usada: str) -> None:
    cuerpo = respuesta.text
    print(f"  cuerpo: {tapar(cuerpo)[:300]}")
    print(
        f"  ¿repite la clave usada?: {'SÍ' if clave_usada and clave_usada in cuerpo else 'no'}"
    )


def gnews() -> None:
    base = "https://gnews.io/api/v4/"
    campos = {
        "titulo": lambda noticia: noticia.get("title"),
        "fecha": lambda noticia: noticia.get("publishedAt"),
        "medio": lambda noticia: (noticia.get("source") or {}).get("name"),
        "idioma": lambda noticia: noticia.get("lang"),
    }
    print(f"\n== GNews · /search, q={TEMA!r}, lang=es")
    respuesta = pedir(
        base + "search", {"q": TEMA, "lang": "es", "max": 10, "apikey": GNEWS}
    )
    if respuesta.is_success:
        datos = respuesta.json()
        print(f"  totalArticles: {datos.get('totalArticles')}")
        resumir(datos.get("articles", []), *campos.values())
    else:
        error(respuesta, GNEWS)
    time.sleep(PAUSA_GNEWS)

    print("\n== GNews · /top-headlines, sin tema, lang=es")
    respuesta = pedir(
        base + "top-headlines", {"lang": "es", "max": 10, "apikey": GNEWS}
    )
    if respuesta.is_success:
        resumir(respuesta.json().get("articles", []), *campos.values())
    else:
        error(respuesta, GNEWS)
    time.sleep(PAUSA_GNEWS)

    hace_30 = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hace_25 = (datetime.now(UTC) - timedelta(days=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n== GNews · /search de hace 30 a 25 días (from={hace_30}, to={hace_25})")
    respuesta = pedir(
        base + "search",
        {
            "q": TEMA,
            "lang": "es",
            "max": 10,
            "from": hace_30,
            "to": hace_25,
            "apikey": GNEWS,
        },
    )
    if respuesta.is_success:
        resumir(respuesta.json().get("articles", []), *campos.values())
    else:
        error(respuesta, GNEWS)
    time.sleep(PAUSA_GNEWS)

    print("\n== GNews · una clave que no existe")
    respuesta = pedir(base + "search", {"q": TEMA, "lang": "es", "apikey": CLAVE_FALSA})
    error(respuesta, CLAVE_FALSA)


def newsdata() -> None:
    base = "https://newsdata.io/api/1/"
    campos = {
        "titulo": lambda noticia: noticia.get("title"),
        "fecha": lambda noticia: noticia.get("pubDate"),
        "medio": lambda noticia: noticia.get("source_name") or noticia.get("source_id"),
        "idioma": lambda noticia: noticia.get("language"),
    }
    print(f"\n== NewsData.io · /latest, q={TEMA!r}, language=es")
    respuesta = pedir(
        base + "latest", {"q": TEMA, "language": "es", "apikey": NEWSDATA}
    )
    if respuesta.is_success:
        datos = respuesta.json()
        print(
            f"  status: {datos.get('status')} · totalResults: {datos.get('totalResults')} · nextPage: {'sí' if datos.get('nextPage') else 'no'}"
        )
        resumir(datos.get("results", []), *campos.values())
    else:
        error(respuesta, NEWSDATA)

    print("\n== NewsData.io · /latest, sin tema, language=es")
    respuesta = pedir(base + "latest", {"language": "es", "apikey": NEWSDATA})
    if respuesta.is_success:
        resumir(respuesta.json().get("results", []), *campos.values())
    else:
        error(respuesta, NEWSDATA)

    print("\n== NewsData.io · /latest con timeframe=48 (¿lo admite el plan gratuito?)")
    respuesta = pedir(
        base + "latest",
        {"q": TEMA, "language": "es", "timeframe": 48, "apikey": NEWSDATA},
    )
    if respuesta.is_success:
        resumir(respuesta.json().get("results", []), *campos.values())
    else:
        error(respuesta, NEWSDATA)

    print("\n== NewsData.io · una clave que no existe")
    respuesta = pedir(
        base + "latest", {"q": TEMA, "language": "es", "apikey": CLAVE_FALSA}
    )
    error(respuesta, CLAVE_FALSA)


TEMAS_DE_BUSQUEDA = ("inteligencia artificial", "cambio climático")


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(
        letra for letra in descompuesto if unicodedata.category(letra) != "Mn"
    ).lower()


def contiene(buscado: str, texto: str | None) -> bool:
    """Si `buscado` (ya sin tildes) está en `texto`, sin tildes ni mayúsculas."""
    return buscado in sin_tildes(texto or "")


def busqueda() -> None:
    """¿Son del tema las noticias que devuelve NewsData.io para un tema?

    Visto al probar el cliente (9 oct): con `q="inteligencia artificial"`, la
    primera noticia era sobre un veterano de Malvinas. Cada tema se pide de tres
    formas —tal cual, la frase entre comillas y `qInTitle`— y se cuenta en
    cuántas de las noticias aparece el tema ENTERO, sin tildes ni mayúsculas, en
    el título, en la entradilla y en las palabras clave que trae la noticia. Es
    una cota baja: una noticia de IA que sólo diga «IA» no cuenta, y por eso se
    imprimen los titulares, para leerlos.
    """
    url = "https://newsdata.io/api/1/latest"
    for tema in TEMAS_DE_BUSQUEDA:
        buscado = sin_tildes(tema)
        for forma, parametros in (
            ("q tal cual", {"q": tema}),
            ("q entre comillas", {"q": f'"{tema}"'}),
            ("qInTitle", {"qInTitle": tema}),
        ):
            print(f"\n== NewsData.io · {tema!r}, {forma}")
            respuesta = pedir(url, {**parametros, "language": "es", "apikey": NEWSDATA})
            if not respuesta.is_success:
                error(respuesta, NEWSDATA)
                continue
            datos = respuesta.json()
            noticias = datos.get("results") or []
            en_titulo = [
                contiene(buscado, noticia.get("title")) for noticia in noticias
            ]
            en_entradilla = [
                contiene(buscado, noticia.get("description")) for noticia in noticias
            ]
            en_claves = [
                contiene(buscado, " ".join(noticia.get("keywords") or []))
                for noticia in noticias
            ]
            en_alguno = [
                titulo or entradilla
                for titulo, entradilla in zip(en_titulo, en_entradilla, strict=True)
            ]
            print(
                f"  totalResults {datos.get('totalResults')}; {len(noticias)} noticias; "
                f"el tema en el título {sum(en_titulo)}, en la entradilla "
                f"{sum(en_entradilla)}, en alguno de los dos {sum(en_alguno)}, "
                f"en las palabras clave {sum(en_claves)}"
            )
            for noticia, esta in zip(noticias, en_alguno, strict=True):
                marca = "✓" if esta else "·"
                print(f"    {marca} {tapar(str(noticia.get('title')))[:90]}")


def main() -> None:
    if not GNEWS or not NEWSDATA:
        raise SystemExit("Faltan GNEWS_API_KEY o NEWSDATA_API_KEY en el .env.")
    parte = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if parte not in ("todo", "busqueda"):
        raise SystemExit(f"Parte desconocida: {parte!r} (todo | busqueda).")
    print(f"== {datetime.now(UTC).isoformat(timespec='seconds')} · {parte}")
    if parte == "busqueda":
        busqueda()
        return
    gnews()
    newsdata()


if __name__ == "__main__":
    main()
