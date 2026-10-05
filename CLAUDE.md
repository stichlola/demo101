# Note di progetto

## Preferenze dell'utente (sempre)

- **Mostra sempre il risultato con delle foto.** Dopo ogni modifica a un modello
  3D o a una scena Blender, renderizza delle immagini di anteprima (fronte, 3/4,
  dettaglio) e mandale all'utente prima di chiudere il lavoro.
- Rispondi in italiano.
- Lavora sempre in Blender (script Python eseguiti con `blender -b -P ...`).

## Progetti

- `blender/`: animazione "rat dance" (goblin che fa breakdance su un isolotto
  in un vulcano, scheletri che ballano dietro). Vedi `blender/README.md`.
- `print/`: oggetti per la stampa 3D. `print/scripts/emboss_text.py` aggiunge
  una scritta corsiva in rilievo sul cilindro `models/base.stl` (stampa in
  vase mode); `models/tappo.stl` è il tappo. `print/scripts/pippo_rider.py`
  sposta il mini personaggio dalla testa del golem "Pippo" alle sue spalle,
  ricostruendo le gambe. Vedi `print/README.md`.
