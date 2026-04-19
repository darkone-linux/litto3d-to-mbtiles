#!/usr/bin/env python3

import os
import re
import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
LITTO3D_SCRIPT = SCRIPT_DIR / "litto3d_to_mbtiles.py"


def run(cmd: list[str]):
    """Exécute une commande et laisse sa sortie s'afficher directement."""
    subprocess.run(cmd, check=False)


def check_created(path: Path):
    if not path.exists():
        print(f"Erreur : le fichier destination n'a pas été créé : {path}", file=sys.stderr)


def step1(source: Path, destination: Path):
    print("=== Étape 1 : grosse tuile basse définition (zoom 10-16) ===")
    dest_file = destination / "16-global.mbtiles"
    if dest_file.exists():
        print(f"  {dest_file.name} existe déjà, on passe.")
        return
    run([
        "python3", str(LITTO3D_SCRIPT),
        str(source),
        str(dest_file),
        "--zoom-min", "10",
        "--zoom-max", "16",
    ])
    check_created(dest_file)


def step2(source: Path, destination: Path):
    print("=== Étape 2 : tuiles intermédiaires moyenne définition (zoom 17-18) ===")
    pattern = re.compile(r"^\d{4}_\d{4}$")
    subdirs = sorted([d for d in source.iterdir() if d.is_dir() and pattern.match(d.name)])

    if not subdirs:
        print("  Aucun sous-dossier correspondant trouvé.")
        return

    for subdir in subdirs:
        dest_file = destination / f"18-{subdir.name}.mbtiles"
        if dest_file.exists():
            print(f"  {dest_file.name} existe déjà, on passe.")
            continue
        print(f"  Traitement de {subdir.name}...")
        run([
            "python3", str(LITTO3D_SCRIPT),
            str(subdir),
            str(dest_file),
            "--zoom-min", "17",
            "--zoom-max", "18",
        ])
        check_created(dest_file)


def step3(source: Path, destination: Path):
    print("=== Étape 3 : petites tuiles haute définition (zoom 19-20) ===")
    level1_pattern = re.compile(r"^\d{4}_\d{4}$")
    level2_pattern = re.compile(r".*_UTM21N_RGSPM06_DANGER50$")

    matches = []
    for level1_dir in sorted(source.iterdir()):
        if not level1_dir.is_dir() or not level1_pattern.match(level1_dir.name):
            continue
        for level2_dir in sorted(level1_dir.iterdir()):
            if level2_dir.is_dir() and level2_pattern.match(level2_dir.name):
                matches.append((level1_dir.name, level2_dir.name))

    if not matches:
        print("  Aucun chemin correspondant trouvé.")
        return

    for dir_level1, dir_level2 in matches:
        dest_file = destination / f"20-{dir_level1}-{dir_level2}.mbtiles"
        if dest_file.exists():
            print(f"  {dest_file.name} existe déjà, on passe.")
            continue
        print(f"  Traitement de {dir_level1}/{dir_level2}...")
        run([
            "python3", str(LITTO3D_SCRIPT),
            str(source / dir_level1 / dir_level2),
            str(dest_file),
            "--zoom-min", "19",
            "--zoom-max", "20",
        ])
        check_created(dest_file)


def main():
    if len(sys.argv) != 3:
        print(f"Usage : python3 {sys.argv[0]} <source> <destination>", file=sys.stderr)
        sys.exit(1)

    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])

    # Validation des arguments
    if not source.is_dir():
        print(f"Erreur : le dossier source n'existe pas ou n'est pas un dossier : {source}", file=sys.stderr)
        sys.exit(1)
    if not os.access(source, os.R_OK):
        print(f"Erreur : le dossier source n'est pas accessible en lecture : {source}", file=sys.stderr)
        sys.exit(1)
    if not destination.is_dir():
        print(f"Erreur : le dossier destination n'existe pas ou n'est pas un dossier : {destination}", file=sys.stderr)
        sys.exit(1)
    if not os.access(destination, os.R_OK | os.W_OK):
        print(f"Erreur : le dossier destination n'est pas accessible en lecture/écriture : {destination}", file=sys.stderr)
        sys.exit(1)

    step1(source, destination)
    step2(source, destination)
    step3(source, destination)

    print("=== Terminé ===")


if __name__ == "__main__":
    main()
