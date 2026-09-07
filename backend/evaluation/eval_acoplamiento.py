"""¿Cuánto vale que dos señales de *forma* estén de acuerdo? (issue #109)

La dimensión ``forma`` la deciden tres señales: ``detect_clickbait`` (zero-shot,
opaca), ``detect_clickbait_lexical`` (reglas) y ``detect_clickbait_linear``
(regresión logística). Las dos últimas **comparten la extracción de rasgos** —
``linear.featurize_cues()`` llama a ``lexical.detect()`` y reutiliza sus listas—,
cosa ya declarada en la ficha del lineal:

    «No capta engaño semántico (usa las mismas pistas de superficie que el
    léxico).»

Lo que no estaba escrito es **la consecuencia sobre el contraste**: si dos de las
tres no son observaciones independientes, su acuerdo no vale lo mismo que el de
dos señales distintas, y el sistema hoy lo cuenta igual.

Esto lo convierte en un número.

QUÉ SE MIDE, y por qué no basta con «coinciden mucho»

Dos clasificadores buenos sobre un dataset fácil coinciden mucho aunque sean
independientes, así que el acuerdo bruto no distingue nada. Hacen falta dos
lecturas más:

1. **Kappa de Cohen** — el acuerdo que SOBRA sobre el que cabría esperar por azar
   dadas sus tasas individuales. Responde «¿se parecen más de lo que su propia
   precisión explica?».

2. **Correlación de errores** — la que de verdad importa aquí. Dos señales
   independientes se equivocan en titulares DISTINTOS; dos acopladas se equivocan
   en los mismos. Se compara ``P(lineal falla | léxico falla)`` con
   ``P(lineal falla)`` a secas: si son parecidas, saber que una falló no dice
   nada de la otra —independientes—; si la primera es mucho mayor, fallan juntas.

Se corre sobre **dev**, nunca sobre test: éste sigue congelado para el número
final.

    python -m backend.evaluation.eval_acoplamiento
    python -m backend.evaluation.eval_acoplamiento --con-zero-shot 300
"""

import asyncio
import contextlib
import json
import sys
from pathlib import Path

from backend.evaluation.splits import load_split
from backend.integrations.nlp import lexical, linear

_RAIZ = Path(__file__).resolve().parents[2]


def predicciones(headlines: list[str]) -> tuple[list[int], list[int]]:
    """Veredicto de cada señal sobre cada titular, como 0/1."""
    lex, lin = [], []
    for h in headlines:
        lex.append(int(lexical.detect(h).data["is_clickbait"]))
        lin.append(int(linear.predict(h).data["is_clickbait"]))
    return lex, lin


def acuerdo(a: list[int], b: list[int]) -> dict:
    """Acuerdo observado, esperado por azar, y kappa de Cohen."""
    n = len(a)
    observado = sum(x == y for x, y in zip(a, b, strict=True)) / n

    # Esperado por azar: que ambas digan 1 por su cuenta, más que ambas digan 0.
    pa, pb = sum(a) / n, sum(b) / n
    esperado = pa * pb + (1 - pa) * (1 - pb)

    kappa = (observado - esperado) / (1 - esperado) if esperado < 1 else float("nan")
    return {"observado": observado, "esperado": esperado, "kappa": kappa}


def correlacion_de_errores(a: list[int], b: list[int], y: list[int]) -> dict:
    """¿Fallan en los mismos titulares?

    Si fueran independientes, ``P(b falla | a falla)`` sería igual a
    ``P(b falla)``: saber que una se equivocó no diría nada de la otra.
    """
    fallos_a = [i for i in range(len(y)) if a[i] != y[i]]
    fallos_b = [i for i in range(len(y)) if b[i] != y[i]]
    ambos = set(fallos_a) & set(fallos_b)

    p_b = len(fallos_b) / len(y)
    p_b_dado_a = len(ambos) / len(fallos_a) if fallos_a else float("nan")

    return {
        "fallos_a": len(fallos_a),
        "fallos_b": len(fallos_b),
        "ambos": len(ambos),
        "esperados_si_independientes": len(fallos_a) * p_b,
        "p_b": p_b,
        "p_b_dado_a": p_b_dado_a,
    }


def muestra_estratificada(pares: list[tuple[str, int]], n: int, semilla: int = 24):
    """Submuestra conservando la proporción de clases del split.

    Hace falta muestrear porque la tercera señal —zero-shot sobre
    BART-large-MNLI— tarda ~1 s por titular en CPU: los 6400 de dev serían casi
    dos horas. Se estratifica para que la muestra no cambie la dificultad del
    problema respecto al split completo.
    """
    import random

    rnd = random.Random(semilla)
    por_clase: dict[int, list[tuple[str, int]]] = {}
    for par in pares:
        por_clase.setdefault(par[1], []).append(par)

    muestra = []
    for items in por_clase.values():
        cuantos = round(n * len(items) / len(pares))
        muestra.extend(rnd.sample(items, min(cuantos, len(items))))
    rnd.shuffle(muestra)
    return muestra


async def zero_shot(headlines: list[str]) -> list[int]:
    """Veredicto de la señal OPACA, la única independiente de las otras dos.

    Importa la factoría aquí dentro y no arriba para que el resto del script no
    cargue ningún modelo: sin esto, medir el acuerdo entre léxico y lineal —que
    son regex y un producto escalar— arrastraría 1,6 GB de BART.
    """
    from backend.integrations.nlp.factory import get_nlp_backend

    api = get_nlp_backend()
    modelo = "facebook/bart-large-mnli"
    etiquetas = ["clickbait", "factual news"]

    veredictos = []
    for i, h in enumerate(headlines, 1):
        resultado = await api.zero_shot(h, modelo, etiquetas)
        # Sin esto, un fallo del backend a mitad de corrida revienta con un
        # TypeError opaco al indexar `data`, que es None, y tira por la borda
        # los minutos ya invertidos sin decir qué pasó.
        if not resultado.has_content():
            raise RuntimeError(
                f"la señal falló en el titular {i}/{len(headlines)}: {resultado.error}"
            )
        veredictos.append(int(resultado.data["label"] == "clickbait"))
        if i % 50 == 0:
            print(f"    ...{i}/{len(headlines)}", flush=True)
    return veredictos


def zero_shot_cacheado(headlines: list[str], n: int, semilla: int) -> list[int]:
    """Igual que ``zero_shot`` pero guardando el resultado en disco.

    Clasificar 300 titulares con BART cuesta minutos y el resultado es
    determinista, así que recalcularlo en cada análisis es tiempo tirado. La
    caché va en ``var/`` y no en ``data/`` por el criterio de siempre: es un
    derivado regenerable, no un dato del proyecto.

    La clave incluye tamaño y semilla porque son lo que determina QUÉ titulares
    entran en la muestra: reutilizar la caché con otra muestra daría un resultado
    silenciosamente equivocado.
    """
    cache = _RAIZ / "var" / f"zero_shot_dev_{n}_{semilla}.json"
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado["headlines"] == headlines:
            print(f"    (reusando {cache.name})")
            return guardado["veredictos"]
        print("    (la caché no corresponde a esta muestra: recalculando)")

    veredictos = asyncio.run(zero_shot(headlines))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"headlines": headlines, "veredictos": veredictos}),
        encoding="utf-8",
    )
    return veredictos


def veredicto_forma(lex: int, lin: int, zs: int) -> bool | None:
    """Reproduce la agregación real: cualquier discrepancia deja la dimensión
    sin resolver. No hay mayoría — ver ``analysis/orchestrator._aggregate``."""
    distintos = {lex, lin, zs}
    return bool(next(iter(distintos))) if len(distintos) == 1 else None


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


if __name__ == "__main__":
    headlines, y = zip(*load_split("dev"), strict=True)
    headlines, y = list(headlines), list(y)
    print(f"dev: {len(headlines)} titulares\n")

    lex, lin = predicciones(headlines)

    exactitud_lex = sum(p == t for p, t in zip(lex, y, strict=True)) / len(y)
    exactitud_lin = sum(p == t for p, t in zip(lin, y, strict=True)) / len(y)
    print("ACIERTO POR SEPARADO")
    print(f"  lexical  {_pct(exactitud_lex)}")
    print(f"  linear   {_pct(exactitud_lin)}\n")

    a = acuerdo(lex, lin)
    print("ACUERDO ENTRE LAS DOS")
    print(f"  observado           {_pct(a['observado'])}")
    print(f"  esperado por azar   {_pct(a['esperado'])}")
    print(f"  kappa de Cohen      {a['kappa']:.3f}")
    print("    (0 = como el azar · 1 = idénticas)\n")

    e = correlacion_de_errores(lex, lin, y)
    print("¿FALLAN EN LOS MISMOS TITULARES?")
    print(f"  falla lexical            {e['fallos_a']}")
    print(f"  falla linear             {e['fallos_b']}")
    print(f"  fallan LAS DOS a la vez  {e['ambos']}")
    print(
        f"    esperados si fueran independientes: {e['esperados_si_independientes']:.0f}\n"
    )
    print(f"  P(linear falla)                 {_pct(e['p_b'])}")
    print(f"  P(linear falla | lexical falla) {_pct(e['p_b_dado_a'])}")
    print("    (parecidas = independientes · muy distintas = fallan juntas)")

    # ------------------------------------------------------------------
    # El contraste: ¿discrepa MÁS con la señal opaca, que sí es independiente?
    #
    # Sin esta comparación, un 94 % de acuerdo no significa nada: quizá el
    # dataset es fácil y CUALQUIER par coincidiría igual. Lo que da sentido al
    # número es ver cuánto se separan dos señales que no comparten rasgos.
    #
    # Va detrás de un argumento porque carga BART y tarda minutos.
    # ------------------------------------------------------------------
    if "--con-zero-shot" in sys.argv:
        cuantos = 300
        for i, arg in enumerate(sys.argv):
            if arg == "--con-zero-shot" and i + 1 < len(sys.argv):
                with contextlib.suppress(ValueError):
                    cuantos = int(sys.argv[i + 1])

        muestra = muestra_estratificada(list(zip(headlines, y, strict=True)), cuantos)
        h_m, y_m = [p[0] for p in muestra], [p[1] for p in muestra]

        print(f"\n\nCONTRASTE CON LA SEÑAL INDEPENDIENTE ({len(h_m)} titulares)")
        print("  cargando BART-large-MNLI y clasificando...")
        zs = zero_shot_cacheado(h_m, len(h_m), 24)

        lex_m, lin_m = predicciones(h_m)

        # El acierto de cada una SOBRE LA MUESTRA es lo que distingue las dos
        # lecturas posibles de una discrepancia alta: una señal puede discrepar
        # porque mira otra cosa (diversidad útil) o porque se equivoca (ruido).
        # Sin esto, un 36 % de discrepancia no se puede interpretar.
        print("\n  acierto sobre esta muestra:")
        for etiqueta, pred in (
            ("lexical", lex_m),
            ("linear", lin_m),
            ("zero-shot", zs),
        ):
            exacto = sum(p == t for p, t in zip(pred, y_m, strict=True)) / len(y_m)
            print(f"    {etiqueta:12} {_pct(exacto)}")

        parejas = {
            "lexical vs linear  (ACOPLADAS)": (lex_m, lin_m),
            "lexical vs zero-shot": (lex_m, zs),
            "linear  vs zero-shot": (lin_m, zs),
        }

        print(f"\n  {'pareja':34} {'acuerdo':>9} {'discrepa':>9} {'kappa':>7}")
        for etiqueta, (p, q) in parejas.items():
            a_ = acuerdo(p, q)
            print(
                f"  {etiqueta:34} {_pct(a_['observado']):>9} "
                f"{_pct(1 - a_['observado']):>9} {a_['kappa']:>7.3f}"
            )

        print("\n  Si el par acoplado discrepa MUCHO menos que los otros dos, la")
        print("  diversidad de la dimensión `forma` la aporta una sola señal.")

        # --------------------------------------------------------------
        # Lo que de verdad decide: cuántos análisis quedan sin resolver, y
        # QUIÉN los deja así. La agregación declara `None` ante cualquier
        # discrepancia, sin pesar quién discrepa ni cuánto acierta cada uno.
        # --------------------------------------------------------------
        print(f"\n\nVEREDICTO DE LA DIMENSIÓN `forma` ({len(h_m)} titulares)")

        veredictos = [
            veredicto_forma(a_, b_, c_)
            for a_, b_, c_ in zip(lex_m, lin_m, zs, strict=True)
        ]
        sin_resolver = [i for i, v in enumerate(veredictos) if v is None]
        resueltos = len(h_m) - len(sin_resolver)

        print(f"  resuelto      {resueltos:>4}  ({_pct(resueltos / len(h_m))})")
        print(
            f"  AMBIGUO       {len(sin_resolver):>4}  ({_pct(len(sin_resolver) / len(h_m))})\n"
        )

        # ¿Quién es el disidente en cada caso sin resolver?
        disidentes = {"solo zero-shot": 0, "solo lexical": 0, "solo linear": 0}
        zs_solo_y_equivocado = 0
        for i in sin_resolver:
            trio = (lex_m[i], lin_m[i], zs[i])
            if lex_m[i] == lin_m[i] != zs[i]:
                disidentes["solo zero-shot"] += 1
                # Si además el par acertó, la ambigüedad la fabricó un error.
                if lex_m[i] == y_m[i]:
                    zs_solo_y_equivocado += 1
            elif lin_m[i] == zs[i] != lex_m[i]:
                disidentes["solo lexical"] += 1
            elif lex_m[i] == zs[i] != lin_m[i]:
                disidentes["solo linear"] += 1
            del trio

        print("  quién discrepa en los casos ambiguos:")
        for etiqueta, cuenta in disidentes.items():
            porcion = cuenta / len(sin_resolver) if sin_resolver else 0
            print(f"    {etiqueta:16} {cuenta:>4}  ({_pct(porcion)})")

        print(
            f"\n  de esos, el zero-shot discrepaba SOLO y ADEMÁS se equivocaba: "
            f"{zs_solo_y_equivocado}"
        )
        if sin_resolver:
            print(
                f"    → {_pct(zs_solo_y_equivocado / len(sin_resolver))} de la ambigüedad "
                "total es un error de la señal menos fiable"
            )
