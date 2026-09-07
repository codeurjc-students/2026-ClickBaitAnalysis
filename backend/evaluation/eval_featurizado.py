"""¿Qué ve, y qué NO puede ver, el featurizado del lineal? (issue #109)

``eval_acoplamiento`` midió que el léxico y el lineal coinciden demasiado. Este
mide **por qué**, y la respuesta no está en los pesos sino en el vector de
entrada, que ambas comparten: ``linear.featurize_cues()`` llama a
``lexical.detect()`` y cuenta sus matches.

Tres cosas se derivan de ese vector, y ninguna necesita cargar un modelo:

1. **El veredicto del léxico ES el soporte del vector.** Con ``THRESHOLD = 1`` y
   cada match aportando al menos 1, decir «es clickbait» equivale a decir «algún
   cue disparó». Si eso se cumple, el léxico no es una segunda opinión: es una
   función determinista del *input* del lineal, y su acuerdo no puede leerse como
   corroboración.

2. **El techo de recall.** Un titular cuyo vector sale todo a cero no puede
   detectarse: el lineal responde ``sigmoid(intercepto)`` sin mirar nada, y como
   ``w · 0 = 0`` no hay reentrenamiento que lo cambie. El porcentaje de positivos
   reales en esa situación es un techo duro, y decide si tocan RASGOS (#75) o
   PESOS (#78) — en ese orden.

3. **Cuánto vale el atajo de fuente.** El grupo de vector vacío recibe siempre la
   misma respuesta, así que su acierto mide lo que aporta el mero hecho de que
   dispare algún cue, sin mirar cuál ni con qué peso. Comparado con la tasa base
   del corpus, eso es exactamente el valor del atajo — y comparar esa ganancia
   dentro y fuera de dominio dice si lo aprendido fue clickbait o fue la fuente.

Se corre sobre **dev** (test sigue congelado) y sobre **Webis-17**, porque el
contraste entre los dos corpus es el resultado: los mismos rasgos, dos mundos.

    python -m backend.evaluation.eval_featurizado
"""

from backend.evaluation.eval_acoplamiento import acuerdo, predicciones
from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split
from backend.integrations.nlp import lexical, linear


def vector_vacio(headline: str) -> bool:
    """¿El titular no dispara ningún cue? Entonces el lineal no tiene qué pesar."""
    return not any(linear.featurize_cues(headline))


def es_indicador_de_soporte(headlines: list[str]) -> float:
    """Fracción en que el veredicto del léxico coincide con «el vector tiene algo».

    Un 1.0 significa que el umbral no discrimina nada: el léxico y el soporte del
    vector son el mismo predicado escrito de dos maneras.
    """
    iguales = sum(
        (not vector_vacio(h)) == bool(lexical.detect(h).data["is_clickbait"])
        for h in headlines
    )
    return iguales / len(headlines)


def cobertura(pares: list[tuple[str, int]]) -> dict:
    """Reparto de vectores vacíos, y el techo de recall que implica.

    Se separa por clase porque el agregado engaña: que la mitad de los titulares
    tenga el vector vacío no dice nada malo si son todos negativos. Lo que duele
    es el vacío entre los POSITIVOS, que es clickbait real invisible.
    """
    vacios_pos = vacios_neg = pos = neg = 0
    activos = 0
    for h, y in pares:
        nz = sum(1 for x in linear.featurize_cues(h) if x)
        activos += nz
        if y == 1:
            pos += 1
            vacios_pos += nz == 0
        else:
            neg += 1
            vacios_neg += nz == 0

    n = pos + neg
    return {
        "n": n,
        "vacios": (vacios_pos + vacios_neg) / n,
        "rasgos_activos_por_titular": activos / n,
        "positivos_invisibles": vacios_pos / pos,
        "techo_de_recall": 1 - vacios_pos / pos,
        "negativos_vacios": vacios_neg / neg,
        # Dentro del grupo que recibe la respuesta por defecto («no clickbait»),
        # ¿qué fracción son de verdad negativos? Eso es lo que acierta gratis.
        "acierto_por_defecto": vacios_neg / (vacios_pos + vacios_neg),
        "tasa_base_negativa": neg / n,
    }


def descomposicion_del_acuerdo(pares: list[tuple[str, int]]) -> dict:
    """Acuerdo léxico-lineal separando el punto ciego compartido.

    El kappa global mezcla dos cosas muy distintas. Donde el vector está vacío
    ambas responden «no» por construcción —una por definición, la otra por su
    intercepto negativo—, así que su acuerdo ahí es forzado y no informa de nada.
    El acuerdo que sí se puede interpretar es el del resto.
    """
    headlines = [h for h, _ in pares]
    lex, lin = predicciones(headlines)
    vacio = [vector_vacio(h) for h in headlines]

    def sobre(indices: list[int]) -> dict | None:
        if not indices:
            return None
        a = [lex[i] for i in indices]
        b = [lin[i] for i in indices]
        # Si una de las dos responde SIEMPRE lo mismo dentro del subconjunto, su
        # kappa sale 0 por construcción —el acuerdo observado iguala al esperado
        # por azar— y eso se leería como «independientes», que es justo lo
        # contrario de lo que pasa. Se marca para no imprimir un 0,000 engañoso.
        return {
            "n": len(indices),
            "constante": len(set(a)) == 1 or len(set(b)) == 1,
            **acuerdo(a, b),
        }

    todos = list(range(len(headlines)))
    return {
        "global": sobre(todos),
        "vector_vacio": sobre([i for i in todos if vacio[i]]),
        "vector_con_algo": sobre([i for i in todos if not vacio[i]]),
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def _informe(nombre: str, pares: list[tuple[str, int]]) -> None:
    c = cobertura(pares)
    print(f"\n\n{'=' * 62}\n{nombre}  (n={c['n']})\n{'=' * 62}")

    print("\nCOBERTURA DEL VECTOR")
    print(f"  vectores todo-cero            {_pct(c['vacios'])}")
    print(f"  rasgos activos por titular    {c['rasgos_activos_por_titular']:.2f}")

    print("\nTECHO DE RECALL  (w · 0 = 0: ningún peso lo levanta)")
    print(f"  positivos reales invisibles   {_pct(c['positivos_invisibles'])}")
    print(f"  techo alcanzable              {_pct(c['techo_de_recall'])}")

    print("\nVALOR DEL ATAJO  (cuánto aporta que dispare ALGÚN cue)")
    print(f"  acierto por defecto           {_pct(c['acierto_por_defecto'])}")
    print(f"  tasa base de la mayoritaria   {_pct(c['tasa_base_negativa'])}")
    ganancia = c["acierto_por_defecto"] - c["tasa_base_negativa"]
    print(f"  ganancia sobre no mirar       {ganancia * 100:+.1f} pts")

    d = descomposicion_del_acuerdo(pares)
    print("\nACUERDO LÉXICO-LINEAL, DESCOMPUESTO")
    print(f"  {'subconjunto':22} {'n':>6} {'acuerdo':>9} {'kappa':>8}")
    for etiqueta, clave in (
        ("global", "global"),
        ("vector vacío", "vector_vacio"),
        ("vector con algo", "vector_con_algo"),
    ):
        s = d[clave]
        if s is None:
            continue
        k = "—" if s["constante"] else f"{s['kappa']:.3f}"
        print(f"  {etiqueta:22} {s['n']:>6} {_pct(s['observado']):>9} {k:>8}")

    print("  — = una de las dos es constante ahí, y su kappa no significa nada:")
    print("      con el vector vacío ambas dicen «no»; con el vector lleno el")
    print("      léxico dice «sí» siempre, porque su veredicto ES el soporte.")


if __name__ == "__main__":
    pesos = linear.JSON
    intercepto = pesos["intercept"]
    print("EL MODELO LINEAL, POR DENTRO")
    print(f"  rasgos                        {len(pesos['weights'])}")
    print(f"    categorías estructurales    {len(lexical.PATTERNS)}")
    print(f"    cues léxicos                {len(lexical.ALL_CUES)}")
    print(f"  intercepto                    {intercepto:.4f}")
    print(f"  p(clickbait) con vector cero  {linear._sigmoid(intercepto):.4f}")
    print("    -> por debajo de 0.5: la respuesta por defecto es «no clickbait»")

    dev = load_split("dev")
    headlines_dev = [h for h, _ in dev]

    print("\n\n¿EL VEREDICTO DEL LÉXICO ES EL SOPORTE DEL VECTOR?")
    coincidencia = es_indicador_de_soporte(headlines_dev)
    print(f"  lexical.is_clickbait == any(featurize_cues(h))   {_pct(coincidencia)}")
    print(f"  (THRESHOLD = {lexical.THRESHOLD}; cada match aporta al menos 1)")
    if coincidencia == 1.0:
        print("  -> son el MISMO predicado: el léxico no aporta un bit nuevo")

    _informe("CHAKRABORTY dev", dev)
    _informe(
        "WEBIS-17 (externo, sin adaptación)", [(h, y) for h, y, _ in load_external()]
    )

    print("\n\nLECTURA")
    print("  Si la ganancia del atajo se desploma fuera de dominio mientras la")
    print("  cobertura se mantiene, lo aprendido no es clickbait: es la fuente.")
