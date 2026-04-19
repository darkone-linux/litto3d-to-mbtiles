# Introduction

Créer un programme python dont l'usage est le suivant :

python3 update-mbtiles.py <source> <destination>

- <source> est un dossier source existant
- <destination> est un dossier destination existant

Ce programme fait appel à un script "litto3d_to_mbtiles.py", situé dans le même dossier que "update-mbtiles.py", qui lit des données litto3d (lidar) situées dans <source> et crée un fichier mbtiles dans <destination>, conformément aux options spécifiées.

En résumé, ce script va créer : 

- Une grosse tuile (fichier) mbtile basse définition, zoom 10 à 16.
- Des tuiles intermédiaires moyenne définition, zoom 17 à 18.
- Des petites tuiles haute définition, zoom 19 à 20.

Ce programme ne crée que les tuiles qui n'existent pas, si les fichiers destination existent déjà, on continue.

# Description du programme

Le programme fait ceci...

## Etape 1, la grosse tuile base définition

Executer la commande suivante, uniquement si "<destination>/16-global.mbtiles" n'existe pas : 

python3 litto3d_to_mbtiles.py "<source>" "<destination>/16-global.mbtiles" --zoom-max 16

## Etape 2, les tuiles intermédiaires moyenne définition

Pour tous les dossiers <subDir> contenus dans le répertoire <source>, qui sont de la forme "[0-9]{4}_[0-9]{4}" : 

- Si "<destination>/18-<subDir>.mbtiles" existe, continuer sans rien faire, sinon...
- Exécuter la commande suivante : 
  - python3 litto3d_to_mbtiles.py "<source>/<subDir>" "<destination>/18-<subDir>.mbtiles" --zoom-min 17 --zoom-max 18
- Vérifier que le fichier "<destination>/18-<subDir>.mbtiles" a bien été créé (existe)

## Etape 3, les petites tuiles haute définition

- Matcher tous les chemins dans <source>, dont les dossiers de 2ème niveau matchent "*_UTM21N_RGSPM06_DANGER50". Extraire le nom du dossier de niveau 1 <dirLevel1> et celui de niveau 2 <dirLevel2>. Exemple :
  - Chemin matché : <source>/0555_5180/LITTO3D_SPM_0557_5177_20241001_UTM21N_RGSPM06_DANGER50
  - Dans cet exemple, le dossier de niveau 1 <dirLevel1> est "0555_5180"
  - Et le dossier de niveau 2 <dirLevel2> est "LITTO3D_SPM_0557_5177_20241001_UTM21N_RGSPM06_DANGER50"
- Pour chaque chemin récupéré :
  - Considérer le fichier <destFile> dont le chemin est <destination>/20-<dirLevel1>-<dirLevel2>.mbtiles
  - Si <destFile> existe, continuer sans rien faire, sinon...
    - Lancer la commande "python3 litto3d_to_mbtiles.py "<source>/<dirLevel1>/<dirLevel2>" "<destFile>" --zoom-min 19 --zoom-max 20"
    - Vérifier si le fichier <destFile> a bien été créé
    - Passer au chemin suivant
