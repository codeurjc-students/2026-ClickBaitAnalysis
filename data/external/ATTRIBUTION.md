# Webis-Clickbait-17 (extractos) — validación externa

Del **Webis Clickbait Corpus 2017** (tuits de 27 medios estadounidenses,
anotados 0–1 por 5 personas vía Amazon Mechanical Turk) se vendorizan **dos
extractos propios**, uno por cada split etiquetado.

## Los dos splits son DISJUNTOS

Webis reparte el corpus en trozos que no se solapan, como cualquier competición:
medido, comparten **un titular de 2 380**. No son dos versiones del mismo
material, son dos trozos distintos, y confundirlos llevaría a evaluar un modelo
sobre su propio entrenamiento.

Cuidado con la nomenclatura: el zip del segundo se llama `clickbait17-train-170630`
pero su carpeta interna se llama `clickbait17-validation-170630`.

| Fichero | Instancias | Split de origen |
|---|---|---|
| `webis17_train170331.jsonl.gz` | 2 459 | `clickbait17-train-170331.zip` (147,8 MB) |
| `webis17_validation170630.jsonl.gz` | 19 484 | `clickbait17-train-170630.zip` (937,1 MB) |

**Extracto original** (#76), una línea = `{"headline": postText, "label": 1 si
truthClass=="clickbait" si no 0, "truthMean": media de anotadores}`.

**Extracto ampliado** (#121) añade dos campos y descarta la basura:

- `id` — sin él, cruzar los dos splits obliga a comparar por texto normalizado.
- `truthJudgments` — los **cinco juicios individuales**, no sólo su media. Es lo
  que permite medir el acuerdo entre anotadores y con él el techo de la tarea
  (`backend/evaluation/eval_ambiguedad.py`): 34,9 % de unanimidad, F1 0,665 de un
  anotador contra el consenso.
- Se descartan **54 instancias con `postText` vacío** (19 538 → 19 484).

Los **cuerpos de artículo** (`targetParagraphs`, 29 MB) NO se versionan: van a
`var/`, gitignorados y regenerables con
`python -m backend.evaluation.webis_extract <zip>`. Ahí va también `targetTitle`
—el titular del artículo, distinto del tuit el 75 % de las veces— y a propósito
lejos del fichero que consumen las señales: la anotación humana se hizo sobre el
TUIT, así que usarlo con esa etiqueta sería etiquetar mal.

## Origen
Zenodo: https://zenodo.org/records/5530410
Ficha del corpus: https://webis.de/data/webis-clickbait-17.html

SHA-256 de `clickbait17-train-170630.zip` (937 094 590 bytes), verificado en la
descarga del 2026-08-26:
`6973ff3e9798aa796f9bf46dc0614536d2e46e1930c1583d30390e147e75e748`

## Licencia
**Creative Commons Attribution 4.0 International (CC BY 4.0)** — redistribución
permitida conservando la atribución.

## Cita (obligatoria por CC BY)
Martin Potthast, Tim Gollub, Kristof Komlossy, Sebastian Schuster, Matti
Wiegmann, Erika Patricia Garces Fernandez, Matthias Hagen, and Benno Stein.
*"Crowdsourcing a Large Corpus of Clickbait on Twitter."* In Proceedings of the
27th International Conference on Computational Linguistics (COLING 2018).

```bibtex
@inproceedings{potthast2018crowdsourcing,
  title={Crowdsourcing a Large Corpus of Clickbait on Twitter},
  author={Potthast, Martin and Gollub, Tim and Komlossy, Kristof and Schuster, Sebastian and Wiegmann, Matti and Garces Fernandez, Erika Patricia and Hagen, Matthias and Stein, Benno},
  booktitle={Proceedings of the 27th International Conference on Computational Linguistics (COLING 2018)},
  pages={1498--1507},
  year={2018}
}
```
