# Webis-Clickbait-17 (extracto) — validación externa

Fichero: `webis17_train170331.jsonl.gz` — 2 459 muestras derivadas del conjunto
etiquetado `clickbait17-train-170331` del **Webis Clickbait Corpus 2017**
(tuits de 27 medios estadounidenses, anotados 0–1 por 5 personas vía
Amazon Mechanical Turk).

Extracto propio: una línea = `{"headline": postText, "label": 1 si
truthClass=="clickbait" si no 0, "truthMean": media de anotadores}`. Se
descartan medios (imágenes) y campos `target*`.

## Origen
Zenodo: https://zenodo.org/records/5530410 (fichero `clickbait17-train-170331.zip`)
Ficha del corpus: https://webis.de/data/webis-clickbait-17.html

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
