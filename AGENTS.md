# Contexte du projet pour agents IA

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

- `--resolution` -> Résolution MNT à utiliser

### Table des couleurs

La table des couleurs suivante doit être utilisée :

## Prochaines actions à prévoir

### Sondes positives

Étendre la carte aux sondes positives : 

- Ajouter une option `--with-relief` qui ajoute les sondes positives.
- Avec cette option, tous les points sont utilisés.
- La table des couleurs est étendue aux sondes positives.

### Couleurs et relief

Introduire un effet de relief. Le tutoriel suivant explique comment faire avec gdal :

- https://gdal.org/en/release-3.12/tutorials/raster_dtm_tut.html

Il faudra adapter les options de la version utilisée si celles du tutoriel ne fonctionnent pas.
