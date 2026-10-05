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

# Pippo – il mini personaggio a cavallo delle spalle del golem

```bash
cd print
# metti lo STL originale in pippo/src/pippo.stl
blender -b -P scripts/pippo_rider.py -- --preview
```

`scripts/pippo_rider.py`:

1. stacca il mini personaggio che spunta dalla testa del golem con un taglio
   locale in vita (z = 29,35 mm), solo attorno al mini;
2. toglie l'anello rimasto sul cranio e chiude il foro con una membrana
   liscia (rilassamento laplaciano) che segue la curvatura del cranio, poi le dà
   una trama a ciottoli come il resto della testa;
3. raddrizza il busto del mini (`--tilt`, default -25°) e ricostruisce bacino,
   gambe e stivaletti in posa da cavaliere: ginocchia appoggiate sulla nuca,
   stinchi che pendono ai lati della testa;
4. fonde mini e gambe in un unico solido (remesh a voxel 0,025 mm), lo siede
   nell'avvallamento tra testa e schiena (sulle spalle) e lo unisce al golem.

Output in `output/pippo/` (STL non versionati, troppo grandi):

* `pippo_rider.stl` – golem + mini a cavallo, pezzo unico;
* `pippo_golem.stl` – solo il golem con la testa ripulita;
* `pippo_mini.stl` – solo il mini con le gambe nuove;
* `preview_*.png` – foto di anteprima.

Il golem originale ha già una quarantina di bordi non chiusi (difetti del file
sorgente): di solito lo slicer li ripara da solo.
