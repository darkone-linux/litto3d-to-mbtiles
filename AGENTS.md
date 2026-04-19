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

Résumé des couleurs :

- 10m et plus : marron clair -> foncé (relief de terre)
- 2 à 10m : vert clair -> fonçé (non recouvert à marée haute)
- 0 à 2m : jaune -> vert clair (potentiellement recouvert à marée haute)
- -1,5 à 0m : rouge -> noir (zone danger à marée basse)
- -3 à 1,5m : bleu clair -> cyan -> rouge (haut fond navigable)
- -200 à -3m : bleu foncé -> clair (fonds sans dangers)

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

#### Étape 1 : tuile globale basse définition
- Fichier : `large/global-<zone>.mbtiles`
- Zoom : 10-16
- Source : tout (repertoire racine)

#### Étape 2 : tuiles moyennes
- Fichiers : `medium/XXXX_XXXX.mbtiles` (par sous-dossier)
- Zoom : 17-20
- Source : sous-dossiers `XXXX_XXXX` à la racine du dossier source

#### Étape 3 : petite tuiles haute définition
- Fichiers : `small/XXXX_XXXX-YYYYYYYY.mbtiles`
- Zoom : 21-22
- Source : sous-dossiers `XXXX_XXXX/*_UTM21N_RGSPM06_DANGER50`
