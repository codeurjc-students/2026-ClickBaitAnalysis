"""Si una dependencia pesada está instalada, y qué decir cuando no lo está.

**Por qué existe.** Dos de las cinco señales sólo funcionan con paquetes que
`requirements.txt` NO trae: la dedicada necesita `torch` y la incoherencia
`sentence-transformers`. No es un descuido — es la decisión que mantiene ligero
al CI, que mockea los backends y nunca ejecuta un modelo. Instalarlos es trabajo
de la imagen de despliegue.

La consecuencia es que **el estado «falta la dependencia» es normal**, no
excepcional, y por eso merece un mensaje propio en vez de caer en el `except`
genérico de cada señal. Medido el 2026-09-08 sobre una instalación con
`requirements.txt` a secas, esto es lo que decía antes:

- dedicada → ``Error inesperado usando el modelo Stremie/…: name 'torch' is not
  defined``. Un `NameError`, no un `ImportError`: `transformers` avisa por
  consola de que no encuentra PyTorch y después revienta con una variable sin
  definir. Quien lo lee en la pantalla piensa que hay un bug en este código.
- incoherencia → ``Error inesperado calculando incoherencia: No module named
  'sentence_transformers'``. Más claro, pero sigue diciendo *inesperado* de algo
  que se espera, y no dice qué hacer.

**Se pregunta, no se importa.** `find_spec` resuelve el módulo sin ejecutarlo,
así que esto NO deshace los imports perezosos de `local.py` e `incoherence.py`
— que son justo lo que permite que el CI corra sin torch.
"""

from importlib.util import find_spec

# Cómo se instala cada una. La rueda de torch se pide del índice de CPU a
# propósito: son 769 MB frente a 1,2 GB de la variante CUDA, y la máquina de
# despliegue no tiene GPU. Medido el 2026-09-08, junto con lo demás: con esta
# rueda el arranque en frío baja de 52,4 s a 24,2 s y la RAM de 1.645 a 1.201 MB.
COMANDOS = {
    "torch": "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    "sentence_transformers": "pip install sentence-transformers",
}


def motivo_si_falta(paquete: str) -> str | None:
    """El motivo que enseñar si `paquete` no está instalado; `None` si lo está.

    Devuelve el mensaje COMPLETO, no un fragmento, porque quien llama lo usa
    para saltarse su propio «Error inesperado»: el prefijo es la mitad de lo que
    hacía inútil al mensaje viejo.

    El nombre del paquete se escribe con guiones —como se instala— y no con el
    guion bajo del import, que es lo que se teclea en el `pip install` y lo que
    aparece en `requirements.txt`.
    """
    if find_spec(paquete) is not None:
        return None

    instalable = paquete.replace("_", "-")
    comando = COMANDOS.get(paquete, f"pip install {instalable}")

    return (
        f"Esta señal necesita `{instalable}`, y esta instalación no lo trae. "
        "No es una avería: `requirements.txt` no lo incluye a propósito —pesa "
        "cientos de MB y las pruebas lo mockean—, así que lo instala la imagen "
        f"de despliegue. Para habilitarla aquí: {comando}"
    )
