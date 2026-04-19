# Contexte du projet pour agents IA

## Règles de développement

Après toute modification du script, tester systématiquement avec :

```sh
python3 litto3d_to_mbtiles.py test test/test.mbtiles
```

Vérifier l'intégrité des fichiers `.mbtiles` générés.

## Introduction

Ce projet contient deux scripts de conversion des fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN :

- **litto3d_to_mbtiles.py** : conversion 单 fichier ou dossier unique
- **update-mbtiles.py** : pipeline complet multi-niveaux pour cartographie HD

Le résultat doit être de bonne qualité et adapté à une navigation avec un voilier dont le tirant d'eau est de 1,5 mètre.

## Fichiers

- shell.nix : shell Nix qui charge toutes les dépendances et environnements nécessaire au script.
- litto3d_to_mbtiles.py : script de conversion principal
- update-mbtiles.py : script de mise à jour complète (3 étapes)
- AGENTS.md : ce fichier, qui contient les informations importantes pour les agents IA

## Dossiers

- trash : anciens fichiers inutiles (essais) -> ne pas lire son contenu.
- test : jeu de test (fichiers litto3D) à utiliser pour vérifier le script.
- Tous les autres dossiers : contiennent des fichiers litto3D par zone.

## Tester le script

Pour tester le script, utiliser la commande suivante :

```sh
python3 litto3d_to_mbtiles.py test test/test.mbtiles
```

Ce script génère un fichier `test/test.mbtiles` dont il faut vérifier l'intégrité.

## Cahier des charges du script

Le script doit scrupuleusement respecter ces règles.

### Options et arguments (litto3d_to_mbtiles.py)

Usage :

```sh
python3 litto3d_to_mbtiles.py <répertoire_litto3d> <fichier_de_sortie.mbtiles> [options]
```

Options :

- `--resolution` : Résolution MNT à utiliser (1M ou 5M, défaut: 1M)
- `--zoom-min` : Niveau de zoom minimal (défaut: 10)
- `--zoom-max` : Niveau de zoom maximal (défaut: 18)
- `--processes` : Nombre de processus parallèles pour gdal2tiles (défaut: 8)
- `--resampling` : Méthode de rééchantillonnage (bilinear, cubic, lanczos, cubicspline, near, average; défaut: bilinear)
- `--keep-tmp` : Conserver les fichiers temporaires pour debug

### Table des couleurs

La table des couleurs utilisée par gdaldem color-relief (-format : altitude R G B A) :

```
nv   0   0   0   0      # NoData → transparent
100  60  30   0 255     # 100m+ : marron foncé
20  100  60  30 255     # 20-100m : marron foncé → marron
10  120  80  40 255     # 10-20m : marron → vert foncé
5    34 139  34 255     # 5-10m : vert foncé → vert clair
2    50 205  50 255     # 2-5m : vert clair → jaune
0.1 220 220   0 255     # 0.1-2m : jaune
0     0   0   0 255     # 0m : ligne de rivage
-0.5 100   0   0 255    # -0.5-0m : gris foncé
-1   150   0   0 255    # -1--0.5m : gris
-1.5 200   0   0 255    # -1.5--1m : gris clair
-2     0 200 255 255    # -2--1.5m : gris-cyan → cyan
-3     0 150 255 255    # -3--2m : cyan
-4     0  70 255 255    # -4--3m : cyan → bleu
-5     0   0 255 255    # -5--4m : bleu
-6     0   0 200 255    # -6--5m : bleu foncé
-8     0   0 150 255    # -8--6m : bleu foncé
-10    0  15 110 255    # -10--8m : bleu foncé
-15    0  10  80 255    # -15--10m : bleu moyen
-50    0   5  50 255    # -50--15m : bleu
-100   0   2  35 255    # -100--50m : bleu clair
-200   0   0  30 255    # -200--100m : bleu foncé
```

Les valeurs NoData sont rendues transparentes (alpha=0).

L'effet de relief (hillshade) est **toujours** appliqué via une fusion multiplicative (multiply blend) avec les couleurs :

- Formule : `out = clip(color × hillshade / 128, 0, 255)`
- Le hillshade est généré avec `-multidirectional` et `-compute_edges` pour éviter les halos aux bords

### Pipeline de traitement (litto3d_to_mbtiles.py)

Le script exécute les étapes suivantes :

1. **Recherche** récursive des fichiers .asc (MNT 1M ou 5M)
2. **Assemblage** en mosaïque VRT (gdalbuildvrt)
3. **Filtrage** des valeurs NoData (-99999 → NoData interne)
4. **Reprojection** en Web Mercator EPSG:3857 (gdalwarp)
4b. **Sur-échantillonnage** adaptatif (cubicspline) si nécessaire pour éviter la pixelisation aux forts zooms
5. **Colorisation + hillshade + fusion** multiplicative
6. **Export** MBTiles PNG (gdal2tiles + mb-util)

### Script update-mbtiles.py

Ce script génère une cartographie MBTiles multi-niveaux en 3 étapes :

```
python3 update-mbtiles.py <source> <destination>
```

**Usage :** `<source>` = dossier contenant les sous-dossiers LITTO3D, `<destination>` = dossier de sortie

#### Étape 1 : globale basse définition
- Fichier : `1-global.mbtiles`
- Zoom : 10-16
- Portée : tutto il repertoire source

#### Étape 2 : tuiles moyennes
- Fichiers : `2-XXXX_XXXX.mbtiles` (par sous-dossier)
- Zoom : 17-20
- Source : sous-dossiers `XXXX_XXXX` à la racine du dossier source

#### Étape 3 : tuiles haute définition (コメント par défaut)
- Fichiers : `3-XXXX_XXXX-YYYYYYYY.mbtiles`
- Zoom : 21-22
- Source : sous-dossiers `XXXX_XXXX/*_UTM21N_RGSPM06_DANGER50`
