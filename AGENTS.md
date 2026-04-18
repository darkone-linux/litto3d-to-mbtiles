# Contexte du projet pour agents IA

## Règles de développement

Après toute modification du script, tester systématiquement avec :

```sh
python3 litto3d_to_mbtiles.py test test/test.mbtiles --zoom-max 18
python3 litto3d_to_mbtiles.py test test/test_earth.mbtiles --zoom-max 18 --without-earth
```

Vérifier l'intégrité des fichiers `.mbtiles` générés.

## Introduction

Ce script convertit les fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN. Le résultat doit 
être de bonne qualité et adapté à une navigation avec un voilier dont le tirant d'eau est de 1,5 mètre.

## Fichiers

- shell.nix : shell nix qui charge toutes les dépendances et environnements nécessaire au script.
- litto3d_to_mbtiles.py : script de convertion
- AGENTS.md : ce fichier, qui contient les informations importantes pour les agents IA

## Dossiers

- trash : anciens fichiers inutiles (essais) -> ne pas lire son contenu.
- test : jeu de test (fichiers litto3D) à utiliser pour vérifier le script.
- Tous les autres dossiers : contiennent des fichiers litto3D par zone.

## Tester le script

Pour tester le script, utiliser la commande suivante : 

```sh
python3 litto3d_to_mbtiles.py test test/test.mbtiles --zoom-max 18
```

Ce script génère un fichier `test/test.mbtiles` dont il faut vérifier l'intégrité.

## Cahier des charges du script

Le script doit scrupuleusement respecter ces règles.

### Options et arguments

Usage :

```sh
python3 litto3d_to_mbtiles.py <répertoire_litto3d> <fichier_de_sortie.mbtiles> [options]
```

Options :

- `--resolution` : Résolution MNT à utiliser (1M ou 5M, défaut: 1M)
- `--zoom-min` : Niveau de zoom minimal (défaut: 10)
- `--zoom-max` : Niveau de zoom maximal (défaut: 16)
- `--processes` : Nombre de processus parallèles pour gdal2tiles (défaut: 4)
- `--resampling` : Méthode de rééchantillonnage (bilinear, cubic, near, average; défaut: bilinear)
- `--keep-tmp` : Conserver les fichiers temporaires pour debug
- `--without-earth` : Exclure les sondes positives (relief terrestre)

### Table des couleurs

La table des couleurs suivante est utilisée (dégradés) :

- 100 m et + : marron foncé
- 100 à 20 m : marron foncé -> marron 
- 20 à 10 m : marron -> vert foncé
- 10 à 5 m : vert foncé -> vert clair
- 5 à 2 m : vert clair -> jaune
- 2 à +0 m : jaune -> jaune-gris
- -0 à -1 m : gris foncé → gris
- -1 à -1,5 m : gris → gris-cyan
- -1,5 à -2 m : gris-cyan → cyan
- -2 à -3 m : cyan → bleu
- -3 à -5 m : bleu -> bleu foncé
- -5 à -10 m : bleu foncé -> bleu moyen
- -10 à -20 m : bleu moyen -> bleu
- -20 à -30 m : bleu -> bleu clair
- -30 à -50 m : bleu clair -> bleu foncé
- -50 à -100 m : bleu foncé -> bleu très foncé
- -100 et en deça : bleu très foncé -> bleu noir (jusqu'à -200m)

Les valeurs NoData sont rendues transparentes.
Sans `--with-relief` : seules les profondeurs (valeurs < 0) sont affichées.
Avec `--with-relief` : les altitudes terrestres positives sont aussi affichées.

L'effet de relief (hillshade) est systématiquement appliqué via un blend HSV avec les couleurs.
