# Rat Dance – scena procedurale Blender

Il ballerino principale (il "ratto", ora il modello **goblin**) fa breakdance su un
grande tavolo di legno in una cucina enorme, mentre un esercito di ballerini di
fila (gli "scarafaggi", ora il modello **skeleton**) balla una coreografia di
salsa alle sue spalle.
La camera fa movimenti aerei coreografati che puntano sempre al ratto, che è il
punto di riferimento della scena.

## Come si genera

Serve Blender 4.2 o superiore.

```bash
cd blender
blender -b -P scripts/build_scene.py -- --out output/rat_dance.blend
```

Il file `output/rat_dance.blend` è già incluso, pronto da aprire, e il video
renderizzato è in `output/rat_dance.mp4` (540×960, 30 fps, EEVEE).

Render in parallelo + montaggio del video:

```bash
for i in 0 1 2; do
  blender -b output/rat_dance.blend -P scripts/render_frames.py -- \
    --out output/render/frames --workers 3 --index $i --scale 50 --samples 8 &
done; wait
blender -b -P scripts/encode_video.py -- --frames output/render/frames --out output/rat_dance.mp4
```

Opzioni utili:

| opzione | default | cosa fa |
|---|---|---|
| `--rat-bvh` | `mocap/breakdance_long_85_12.bvh` | ballo del ratto |
| `--roach-bvh` | `mocap/salsa_60_08.bvh` | coreografia degli scarafaggi |
| `--rat-model` / `--rat-kind` | `models/goblin.glb` / `goblin` | modello del ballerino principale (`''` = ratto placeholder) |
| `--roach-model` / `--roach-kind` | `models/skeleton.glb` / `skeleton` | modello dei ballerini di fila (`''` = scarafaggi placeholder) |
| `--rows` / `--cols` | 3 / 7 | formazione degli scarafaggi |
| `--seed` | 7 | variazioni casuali (rotazioni, antenne) |

Le inquadrature si cambiano in `CAMERA_KEYS` in testa a `scripts/build_scene.py`:
ogni chiave è `(frame, raggio m, azimut°, elevazione°, focale mm)` attorno al
ratto (azimut 0 = davanti al ratto). Tra le chiavi la camera viene interpolata
con una spline morbida e segue il ratto con un target smussato (`CAM_Target`).

## Struttura della scena

| collection | contenuto |
|---|---|
| `SET_Kitchen` | stanza 16×14 m, piastrelle, pareti verdi, finestra, mobili, frigo, fornelli, sedie |
| `SET_Table` | tavolo 3,6×1,9 m (piano a 0,95 m) con cassetto e trappola per topi |
| `LIGHTS` | sole dalla finestra, 3 lampade a sospensione, luce di riempimento |
| `CHAR_Rat` | `RAT_rig` + `RAT_mesh` (goblin) sotto `RAT_rig_root` |
| `CHAR_Roaches` | `ROACH_rig_00…19` + mesh skeleton (+ template nascosto) |
| `CAMERA` | `DanceCam` (Track To su `CAM_Target`) |

Render: 1080×1920 (verticale, come un reel), 30 fps, frame 1–1125 (37,5 s),
EEVEE.

## Scheletri base

Tutti i personaggi usano lo stesso scheletro umanoide con nomi in stile Mixamo
(`Hips`, `Spine`, `Spine1`, `Spine2`, `Neck`, `Head`, `LeftArm`, `LeftForeArm`,
`LeftHand`, `LeftUpLeg`, `LeftLeg`, `LeftFoot`, …), più ossa extra:

* **RAT_rig**: `Snout`, `Ear.L/R`, `Tail1…Tail6`
* **ROACH_rig**: `Antenna1/2.L/R`, `MidLeg1/2.L/R` (le zampe centrali), `Wing.L/R`, `Abdomen`

Le ossa extra hanno un'animazione secondaria procedurale (driver `sin(frame)`).
I balli stanno su strip NLA: gli scarafaggi condividono la stessa action con un
ritardo di 4 frame per fila (effetto "canone").

## Modelli personalizzati (auto-rig)

`scripts/rig_models.py` rigga automaticamente mesh statiche GLB (Z in alto,
rivolte verso -Y, in A-pose), come i due modelli in `models/`:

1. scala il modello sulla lunghezza delle gambe dell'attore mocap;
2. costruisce lo scheletro sulle articolazioni del modello (`LANDMARKS`, in
   unità del modello, lato sinistro, il destro è specchiato);
3. salda i vertici duplicati sulle cuciture UV e fa lo skinning con il bone
   heat di Blender (i vertici che restano senza pesi prendono le ossa più vicine);
4. porta ogni osso nella direzione della posa di riposo della mocap e la
   applica come nuova posa di riposo, copiando anche il roll: così le action
   BVH funzionano sul rig così come sono.

Per il ballerino principale un empty `RAT_rig_root` corregge l'altezza frame per
frame: il goblin è più tozzo dell'attore mocap, quindi nelle mosse a terra
resta appoggiato al tavolo senza compenetrarlo, mentre i salti restano in aria.

Per aggiungere un nuovo modello: aggiungi una voce in `LANDMARKS` (misura le
articolazioni guardando il modello di fronte e di lato) e passa
`--rat-model`/`--rat-kind` o `--roach-model`/`--roach-kind`.

Senza modelli (`--rat-model '' --roach-model ''`) la scena usa ancora il
ratto e gli scarafaggi placeholder fatti di primitive, con ossa extra
(coda, orecchie, antenne, zampe centrali, ali).

## Mocap (librerie gratuite)

Dal [CMU Graphics Lab Motion Capture Database](http://mocap.cs.cmu.edu/),
gratuito per qualunque uso. Convertiti da ASF/AMC a BVH (30 fps, metri) con
`tools/amc2bvh.py`:

| file | clip CMU | contenuto |
|---|---|---|
| `breakdance_long_85_12.bvh` | 85_12 | sequenza breakdance lunga (usata per il ratto) |
| `breakdance_flips_85_14.bvh` | 85_14 | breakdance con flip |
| `breakdance_helicopter_85_08.bvh` | 85_08 | helicopter |
| `breakdance_90_28.bvh` | 90_28 | breakdance |
| `salsa_60_08.bvh` | 60_08 | salsa (usata per gli scarafaggi) |
| `modern_dance_05_02.bvh` | 05_02 | danza moderna, piroette |

Per convertire altre clip CMU:

```bash
python3 tools/amc2bvh.py 85.asf 85_12.amc mocap/nuova_clip.bvh --fps 30
```

> The data used in this project was obtained from mocap.cs.cmu.edu.
> The database was created with funding from NSF EIA-0196217.
