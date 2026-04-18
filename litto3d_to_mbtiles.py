#!/usr/bin/env python3
"""
litto3d_to_mbtiles.py
─────────────────────────────────────────────────────────────────────────────
Convertit les fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN.

Traitement :
  1. Recherche récursive des fichiers .asc (MNT 1M ou 5M)
  2. Assemblage en mosaïque VRT (gdalbuildvrt)
  3. Masquage des valeurs positives (on garde uniquement la bathymétrie < 0)
  4. Reprojection en Web Mercator EPSG:3857 (gdalwarp)
  5. Application d'un dégradé de bleu (gdaldem color-relief)
  6. Export en MBTiles PNG (gdal2tiles + mb-util OU gdal_translate natif)

Dépendances :
  - GDAL (gdalbuildvrt, gdal_calc.py, gdalwarp, gdaldem,
           gdal2tiles.py, gdal_translate, gdaladdo)
  - mb-util (optionnel, recommandé) :  pip install mbutil
    → Si absent, le driver MBTiles natif de GDAL est utilisé en fallback.

Usage :
  python3 litto3d_to_mbtiles.py <répertoire_litto3d> <sortie.mbtiles> [options]

Exemples :
  python3 litto3d_to_mbtiles.py ./LITTO3D_SPM bathymétrie_spm.mbtiles
  python3 litto3d_to_mbtiles.py ./LITTO3D_SPM bathymétrie_spm.mbtiles \\
      --resolution 1M --zoom-min 10 --zoom-max 16 --processes 8
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import subprocess
import shutil
import tempfile
import argparse
from pathlib import Path


# ── Configuration ──────────────────────────────────────────────────────────

# CRS source : UTM zone 21N / RGSPM06 (datum quasi-identique à WGS84 en pratique)
INPUT_CRS = "EPSG:32621"

# CRS cible : Web Mercator (requis pour les tuiles raster standard)
OUTPUT_CRS = "EPSG:3857"

# Valeur NoData à utiliser en interne (les .asc LITTO3D utilisent souvent -99999)
NODATA_INTERNAL = -99999.0

# Table des couleurs pour gdaldem color-relief
# Format : <altitude_m>  <R> <G> <B> <A>
# Valeurs négatives = profondeur sous la mer
# nv = NoData → transparent
COLOR_TABLE = """\
nv 0 0 0 0
0    80  80  80 255
-1   150 150 150 255
-1.5 140 170 170 255
-2     0 255 255 255
-3     0   0 255 255
-10    0   0 150 255
-50    0   5  50 255
"""

# COLOR_TABLE = """\
# nv 0 0 0 0
# 0 200 232 245 255
# -0.5 160 215 238 255
# -1 110 190 230 255
# -2 70 160 215 255
# -3 40 130 195 255
# -5 20 100 175 255
# -7 10 75 150 255
# -10 5 55 125 255
# -15 2 38 100 255
# -20 0 25 80 255
# -30 0 15 65 255
# -50 0 8 50 255
# -100 0 3 35 255
# """


# ── Utilitaires ─────────────────────────────────────────────────────────────

def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande avec affichage et gestion d'erreur."""
    flat = [str(c) for c in cmd]
    print("  $", " ".join(flat))
    return subprocess.run(flat, check=check)


def which(tool: str) -> bool:
    return subprocess.run(["which", tool], capture_output=True).returncode == 0


def check_dependencies() -> None:
    required = ["gdalbuildvrt", "gdal_calc.py", "gdalwarp",
                 "gdaldem", "gdal2tiles.py", "gdal_translate", "gdaladdo"]
    missing = [t for t in required if not which(t)]
    if missing:
        print("❌ Outils GDAL manquants :", ", ".join(missing))
        print("   Installez GDAL : sudo apt install gdal-bin python3-gdal")
        sys.exit(1)
    print("  ✔ GDAL trouvé")
    if which("mb-util"):
        print("  ✔ mb-util trouvé (packaging MBTiles optimal)")
    else:
        print("  ⚠  mb-util absent → fallback driver GDAL natif")
        print("     (Pour l'installer : pip install mbutil)")


def find_asc_files(base_dir: str, resolution: str) -> list[str]:
    """Recherche récursive des fichiers .asc MNT à la résolution demandée."""
    tag = f"_MNT_{resolution}_"
    files = [
        str(p) for p in Path(base_dir).rglob("*.asc")
        if tag in p.name and not p.name.endswith(".aux.xml")
    ]
    return sorted(files)


# ── Pipeline principal ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convertit les fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input_dir",
                        help="Répertoire racine contenant les dossiers LITTO3D")
    parser.add_argument("output",
                        help="Fichier de sortie .mbtiles")
    parser.add_argument("--resolution", default="1M", choices=["1M", "5M"],
                        help="Résolution MNT à utiliser")
    parser.add_argument("--zoom-min", type=int, default=10,
                        help="Niveau de zoom minimal (OpenCPN : 10)")
    parser.add_argument("--zoom-max", type=int, default=16,
                        help="Niveau de zoom maximal (recommandé : 16 pour MNT 1m)")
    parser.add_argument("--processes", type=int, default=4,
                        help="Nombre de processus parallèles pour gdal2tiles")
    parser.add_argument("--resampling", default="bilinear",
                        choices=["bilinear", "cubic", "near", "average"],
                        help="Méthode de rééchantillonnage")
    parser.add_argument("--keep-tmp", action="store_true",
                        help="Conserver les fichiers temporaires (debug)")
    args = parser.parse_args()

    # ── Vérification des prérequis ─────────────────────────────────────────
    print("\n[0/6] Vérification des dépendances...")
    check_dependencies()

    # ── Création du répertoire de travail ──────────────────────────────────
    tmpdir = tempfile.mkdtemp(prefix="litto3d_")
    print(f"\n  Répertoire temporaire : {tmpdir}")

    output_path = args.output
    if not output_path.endswith(".mbtiles"):
        output_path += ".mbtiles"

    try:

        # ── Étape 1 : Recherche des fichiers .asc ─────────────────────────
        print(f"\n[1/6] Recherche des fichiers MNT_{args.resolution}...")
        asc_files = find_asc_files(args.input_dir, args.resolution)
        if not asc_files:
            print(f"❌ Aucun fichier MNT_{args.resolution} trouvé dans {args.input_dir}")
            sys.exit(1)
        print(f"  → {len(asc_files)} fichier(s) trouvé(s) :")
        for f in asc_files:
            print(f"     • {f}")

        # ── Étape 2 : Assemblage VRT ──────────────────────────────────────
        print("\n[2/6] Assemblage en mosaïque VRT...")
        vrt = os.path.join(tmpdir, "mosaic.vrt")
        run([
            "gdalbuildvrt",
            "-a_srs", INPUT_CRS,   # Assigne le CRS source (UTM21N RGSPM06 ≈ WGS84)
            vrt,
            *asc_files,
        ])

        # ── Étape 3 : Masquage des valeurs positives ──────────────────────
        # On conserve uniquement les profondeurs (valeurs < 0)
        # La valeur NoData du fichier source (souvent -99999) est exclue
        print("\n[3/6] Masquage des sondes positives (terre/valeurs NoData)...")
        masked = os.path.join(tmpdir, "masked.tif")
        # Expression : garde A si A est une profondeur valide, sinon → NODATA
        expr = f"numpy.where((A < 0) & (A > {NODATA_INTERNAL}), A, {NODATA_INTERNAL})"
        run([
            "gdal_calc.py",
            "-A", vrt,
            "--outfile", masked,
            "--calc", expr,
            "--NoDataValue", str(NODATA_INTERNAL),
            "--type", "Float32",
            "--co", "COMPRESS=LZW",
            "--co", "TILED=YES",
            "--co", "BLOCKXSIZE=512",
            "--co", "BLOCKYSIZE=512",
            "--overwrite",
        ])

        # ── Étape 4 : Reprojection en Web Mercator ────────────────────────
        print(f"\n[4/6] Reprojection EPSG:32621 → {OUTPUT_CRS}...")
        reprojected = os.path.join(tmpdir, "reprojected.tif")
        run([
            "gdalwarp",
            "-s_srs", INPUT_CRS,
            "-t_srs", OUTPUT_CRS,
            "-r", args.resampling,
            "-srcnodata", str(NODATA_INTERNAL),
            "-dstnodata", str(NODATA_INTERNAL),
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
            "-co", "BLOCKXSIZE=512",
            "-co", "BLOCKYSIZE=512",
            "-multi",
            masked, reprojected,
        ])

        # ── Étape 5 : Dégradé de couleur (bleu clair → bleu foncé) ───────
        print("\n[5/6] Application du dégradé de bleu bathymétrique...")
        color_file = os.path.join(tmpdir, "colors.txt")
        with open(color_file, "w") as fh:
            fh.write(COLOR_TABLE)

        colored = os.path.join(tmpdir, "colored.tif")
        run([
            "gdaldem", "color-relief",
            reprojected,
            color_file,
            colored,
            "-alpha",                 # Canal alpha pour la transparence sur zones terrestres
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
        ])

        # ── Étape 6 : Export MBTiles ──────────────────────────────────────
        print(f"\n[6/6] Génération des tuiles PNG → MBTiles "
              f"(zoom {args.zoom_min}–{args.zoom_max})...")

        if os.path.exists(output_path):
            os.remove(output_path)

        if which("mb-util"):
            # ── Méthode A : gdal2tiles + mb-util (recommandée) ────────────
            # gdal2tiles génère une arborescence de tuiles PNG
            tiles_dir = os.path.join(tmpdir, "tiles")
            run([
                "gdal2tiles.py",
                "--zoom",       f"{args.zoom_min}-{args.zoom_max}",
                "--processes",  str(args.processes),
                "--tiledriver", "PNG",
                "--resampling", args.resampling,
                "--webviewer",  "none",
                "--xyz",        # Schéma XYZ (standard OpenLayers/OpenCPN)
                colored,
                tiles_dir,
            ])
            # mb-util empaquette le répertoire de tuiles en MBTiles
            run([
                "mb-util",
                "--image_format=png",
                "--scheme=xyz",        # Doit correspondre à l'option --xyz ci-dessus
                tiles_dir,
                output_path,
            ])

        else:
            # ── Méthode B : driver MBTiles natif GDAL (fallback) ──────────
            print("  (Utilisation du driver MBTiles GDAL natif)")
            run([
                "gdal_translate",
                "-of", "MBTiles",
                "-co", "TILE_FORMAT=PNG",
                "-co", "ZOOM_LEVEL_STRATEGY=UPPER",
                colored,
                output_path,
            ])
            # Ajout des niveaux de zoom inférieurs via overviews
            # Facteurs pour couvrir zoom_min → zoom_max-1 depuis zoom_max
            factors = [2 ** i for i in range(1, args.zoom_max - args.zoom_min + 1)]
            if factors:
                run([
                    "gdaladdo",
                    "-r", args.resampling,
                    "--config", "USE_RRD", "NO",
                    output_path,
                    *map(str, factors),
                ])

        # ── Résumé ────────────────────────────────────────────────────────
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"\n✅ Terminé !")
        print(f"   Fichier   : {output_path}")
        print(f"   Taille    : {size_mb:.1f} Mo")
        print(f"   Zooms     : {args.zoom_min} – {args.zoom_max}")
        print(f"\n   Pour OpenCPN : Chart Downloads → Import MBTiles")

    except subprocess.CalledProcessError as exc:
        print(f"\n❌ Erreur lors de l'exécution : {exc}")
        sys.exit(1)
    finally:
        if args.keep_tmp:
            print(f"\n   Fichiers temporaires conservés dans : {tmpdir}")
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
