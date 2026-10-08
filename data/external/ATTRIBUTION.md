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

---

# TA1C (extracto) — clickbait en español

Del corpus **TA1C** («Te Ahorré Un Click»: 3 500 tuits de 18 medios en español,
cada uno anotado por tres personas, con un κ de Fleiss de 0,825 y la mayoría
como etiqueta) se vendoriza **un extracto propio** (#229).

| Fichero | Instancias | Origen |
|---|---|---|
| `ta1c.jsonl.gz` | 3 500: `train` 2 100, `validation` 700, `test` 700 | `TA1C_dataset_complete.tar.gz` (6,4 MB) |

Una línea = `{"id", "parte", "medio", "pais", "headline", "label", "anotaciones"}`:

- `headline` es el **Teaser Text**, crudo: el titular, el texto del tuit o los
  dos, según el criterio del corpus, que es lo que leyó quien anotó. No es el
  texto «preprocesado» que el corpus sugiere, porque producción recibe
  titulares crudos.
- `parte` es el **reparto del propio corpus**, no uno nuevo: así las cifras se
  pueden comparar con las publicadas, que se midieron en su `test`.
- `label` es 1 si la mayoría dijo «Clickbait», y `anotaciones`, las **tres
  etiquetas individuales**, como los `truthJudgments` de Webis-17.

Los **artículos** (titular, subtítulo y cuerpo; 5,4 MB) NO se versionan: van a
`var/ta1c/`, gitignorados y regenerables con
`python -m backend.evaluation.ta1c_extract <tarball>`. El cuerpo está vacío en
18 de 3 500. El titular del artículo va con ellos, lejos de los teasers, por lo
mismo que en Webis-17: la anotación se hizo sobre el teaser.

**Dos cosas que conviene saber al usarlo:**

- **Los medios son de 12 países hispanohablantes, más la BBC** (su servicio en
  español, 150 tuits), que la columna de país registra como «Inglaterra»: por
  eso salen 13 valores.
- **La proporción de clickbait cambia mucho de un medio a otro**: del 2,9 %
  (El Universal, Venezuela) al 68,7 % (BBC). La etiqueta es humana, no por medio
  como en Chakraborty, pero un modelo puede aprender a reconocer al medio en vez
  del clickbait: es el vocabulario de fuente que #78 vio con `wikinews`.

## Origen
Repositorio: https://github.com/gmordecki/TA1C (rama `master`; último cambio, el
2024-02-05).

SHA-256 de `TA1C_dataset_complete.tar.gz` (6 359 331 bytes), descargado el
2026-10-07:
`9556954d79142036f71cd6402b12083f2ee5b25b5b704d939d763b93ec31c9a6`

## Licencia
El repositorio lo publica con licencia **MIT**, cuyo texto va abajo porque la
propia licencia exige incluirlo; el artículo lo describe como **CC BY 4.0**. Las
dos permiten redistribuirlo conservando la atribución.

## Cita
Gabriel Mordecki, Guillermo Moncecchi y Javier Couto. *"Te Ahorré Un Click: A
Revised Definition of Clickbait and Detection in Spanish News."*
arXiv:2507.09777, 2025. Según su ficha de arXiv, publicado en *Advances in
Artificial Intelligence – IBERAMIA 2024* (LNCS).

```bibtex
@misc{mordecki2025teahorre,
  title={Te Ahorr{\'e} Un Click: A Revised Definition of Clickbait and Detection in Spanish News},
  author={Mordecki, Gabriel and Moncecchi, Guillermo and Couto, Javier},
  year={2025},
  eprint={2507.09777},
  archivePrefix={arXiv},
  primaryClass={cs.CL}
}
```

## Texto de la licencia MIT del repositorio

```text
MIT License

Copyright (c) 2023 Gabriel Mordecki

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
