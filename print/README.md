# mymusicminis – cilindro con scritta in rilievo (vase mode)

`models/base.stl` (cilindro Ø50 × 40 mm, parete 0,8 mm) e `models/tappo.stl`
(tappo Ø51,2 × 7,2 mm) sono i modelli originali.

```bash
cd print
blender -b -P scripts/emboss_text.py -- --preview
```

Genera in `output/`:

* `base_mymusicminis.stl` – cilindro con la scritta, mesh chiusa (manifold), pronta per lo slicer;
* `base_mymusicminis.blend` – scena Blender con cilindro e tappo;
* `preview_*.png` – foto di anteprima.

La scritta è in corsivo (font [Pacifico](https://fonts.google.com/specimen/Pacifico),
licenza SIL OFL, in `fonts/`), alta 18 mm, lunga circa 90 mm sulla
circonferenza, centrata a metà altezza. Sporge di 1,0 mm e affonda per 0,4 mm
nella parete, così si fonde con il cilindro.

Opzioni: `--text`, `--font`, `--height` (mm), `--max-width` (mm),
`--center-z` (il cilindro va da -20 a +20), `--relief`, `--embed`, `--voxel`.

## Stampa in vase mode

* La scritta è attaccata alla parete in ogni punto: ogni layer ha un solo
  contorno esterno, che la spirale segue anche sopra le lettere.
* Ugello 0,4 mm: i tratti più sottili del corsivo sono circa 1 mm; con una
  larghezza di linea di 0,45 mm vengono riprodotti. Se perdi dettagli, aumenta
  `--height` o prova un'altezza layer di 0,15 mm.
* Il tappo si stampa normalmente (non in vase mode).
