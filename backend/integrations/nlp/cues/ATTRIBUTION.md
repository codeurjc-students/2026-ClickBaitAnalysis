# Listas de pistas léxicas — Chakraborty et al. (2016)

Ficheros usados por `lexical.py` como lexicón del detector:

- `hyperbolic` — 346 palabras hiperbólicas (una por línea) → `WORD_CUES["hyperbole"]`.
- `subjects` — 38 sujetos vagos / referencias hacia delante (literal Python en una
  línea) → `WORD_CUES["forward_reference"]`.
- `common_phrases` — 184 n-gramas frecuentes en clickbait (una frase por línea).
  **No** se cargan como reglas (son n-gramas genéricos pensados como *features* de
  un clasificador); se conservan para el futuro modelo lineal.

## Origen
Repositorio `bhargaviparanjape/clickbait` (carpeta `dependencies/`):
https://github.com/bhargaviparanjape/clickbait

## Licencia
**MIT License** — uso, modificación y redistribución libres conservando el aviso
de copyright y de licencia.

## Cita (OBLIGATORIA para uso en investigación / TFG)
Misma fuente que el dataset (ver `data/ATTRIBUTION.md`):

```bibtex
@inproceedings{chakraborty2016stop,
  title={Stop Clickbait: Detecting and preventing clickbaits in online news media},
  author={Chakraborty, Abhijnan and Paranjape, Bhargavi and Kakarla, Sourya and Ganguly, Niloy},
  booktitle={Advances in Social Networks Analysis and Mining (ASONAM), 2016 IEEE/ACM International Conference on},
  pages={9--16},
  year={2016},
  organization={IEEE}
}
```
