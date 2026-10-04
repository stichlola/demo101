# Rat Dance – scena procedurale Blender

Un ratto fa breakdance su un grande tavolo di legno in una cucina enorme, mentre
un esercito di scarafaggi in piedi balla una coreografia (salsa) alle sue spalle.
La camera fa movimenti aerei coreografati che puntano sempre al ratto, che è il
punto di riferimento della scena.

## Come si genera

Serve Blender 4.2 o superiore.

```bash
cd blender
blender -b -P scripts/build_scene.py -- --out output/rat_dance.blend
```

Il file `output/rat_dance.blend` è già incluso, pronto da aprire.
Un'anteprima a bassa risoluzione (Cycles, 10 fps) si trova in
`preview/rat_dance_preview.mp4`.

Opzioni utili:

| opzione | default | cosa fa |
|---|---|---|
| `--rat-bvh` | `mocap/breakdance_long_85_12.bvh` | ballo del ratto |
| `--roach-bvh` | `mocap/salsa_60_08.bvh` | coreografia degli scarafaggi |
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
| `CHAR_Rat` | `RAT_rig` + parti placeholder |
| `CHAR_Roaches` | `ROACH_rig_00…19` (+ `ROACH_rig_template` nascosto) |
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

I modelli attuali sono solo placeholder rigidi (primitive imparentate alle ossa).

### Sostituire con modelli personalizzati

1. Importa il modello e allinealo allo scheletro in posa di riposo
   (Armature ▸ Pose Position ▸ Rest Position).
2. Cancella le parti placeholder del personaggio.
3. Imparenta la mesh all'armatura (`Ctrl+P` ▸ With Automatic Weights), oppure
   rinomina le ossa del tuo rig con gli stessi nomi e usa le action
   `breakdance_long_85_12` / `salsa_60_08`.

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
