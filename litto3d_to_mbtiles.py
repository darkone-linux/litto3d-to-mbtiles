#!/usr/bin/env python3
"""
litto3d_to_mbtiles.py
─────────────────────────────────────────────────────────────────────────────
Convertit les fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN.

Traitement :
  1. Recherche récursive des fichiers .asc (MNT 1M ou 5M)
  2. Assemblage en mosaïque VRT (gdalbuildvrt)
  3. Filtrage des valeurs NoData internes (gdal_calc.py)
  4. Reprojection en Web Mercator EPSG:3857 (gdalwarp)
  4b. Sur-échantillonnage adaptatif du DEM Float32 (cubicspline)
      pour éviter la pixelisation aux forts niveaux de zoom
  5. Colorisation + hillshade + fusion multiplicative
     - gdaldem color-relief  (dégradé RGBA, alpha=0 sur NoData)
     - gdaldem hillshade     (-compute_edges évite les halos de bord)
     - gdal_calc.py          (multiply blend, alpha strictement préservé)
  6. Export en MBTiles PNG   (gdal2tiles + mb-util OU gdal_translate natif)

Dépendances :
  - GDAL ≥ 3.8 (gdalbuildvrt, gdal_calc.py, gdalwarp, gdaldem,
                gdal2tiles.py, gdal_translate, gdaladdo, gdalinfo)
  - mb-util (optionnel, recommandé) :  pip install mbutil

Usage :
  python3 litto3d_to_mbtiles.py <répertoire_litto3d> <sortie.mbtiles> [options]

Exemples :
  python3 litto3d_to_mbtiles.py ./LITTO3D_SPM bathymétrie_spm.mbtiles
  python3 litto3d_to_mbtiles.py ./LITTO3D_SPM bathymétrie_spm.mbtiles \\
      --resolution 1M --zoom-min 10 --zoom-max 18 --processes 8
─────────────────────────────────────────────────────────────────────────────
"""

import math
import os
import re
import subprocess
import shutil
import sys
import tempfile
import argparse
from pathlib import Path


# ── Configuration ──────────────────────────────────────────────────────────

# CRS source : UTM zone 21N / RGSPM06 (datum quasi-identique à WGS84)
INPUT_CRS = "EPSG:32621"

# CRS cible : Web Mercator (requis pour les tuiles raster standard)
OUTPUT_CRS = "EPSG:3857"

# Valeur NoData interne (les .asc LITTO3D utilisent souvent -99999)
NODATA_INTERNAL = -99999.0

# Facteur d'exagération verticale du hillshade.
# 1 = réaliste mais peu visible sur fond marin plat.
# 3 = bon compromis pour la bathymétrie de Saint-Pierre-et-Miquelon.
HILLSHADE_Z_FACTOR = 3

# Facteur de sur-échantillonnage maximum autorisé (puissance de 2).
# Au-delà de 4×, les fichiers intermédiaires deviennent trop volumineux.
MAX_OVERSAMPLE = 4

# Seuil de ratio (pixel_source / pixel_tuile) en dessous duquel on ne
# sur-échantillonne pas : la résolution native est déjà suffisante.
OVERSAMPLE_THRESHOLD = 2.5

# Table des couleurs pour gdaldem color-relief
# Format : <altitude_m>  <R> <G> <B> <A>
# nv = NoData → transparent (alpha=0)
# Positif  → terre (marron foncé → vert → jaune)
# Négatif  → mer   (gris → cyan → bleu)
COLOR_TABLE = """\
nv 0 0 0 0
300  200 200 200 255
200  170 170 170 255
100   70  70  70 255
30    80  45  10 255
10   110  70  30 255
5     10 100  10 255
3.4   30 150  30 255
3.3  200 200   0 255
3.1  200 200   0 255
3    230 120   0 255
2.4  230 120   0 255
2.3  255  50  50 255
2.1  255  50  50 255
2    140   0   0 255
1.1  140   0   0 255
1     80   0   0 255
0.1   80   0   0 255
0      0   0   0 255
-0.5 100   0  70 255
-1   180   0 130 255
-1.5 250   0 180 255
-2     0 200 255 255
-3     0 150 255 255
-4     0  70 255 255
-5     0   0 255 255
-6     0   0 200 255
-8     0   0 150 255
-10    0  15 110 255
-15    0  10  80 255
-50    0   5  50 255
-100   0   2  35 255
-200   0   0  30 255
"""


# ── Utilitaires ─────────────────────────────────────────────────────────────

def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande avec affichage et gestion d'erreur."""
    flat = [str(c) for c in cmd]
    print("  $", " ".join(flat))
    return subprocess.run(flat, check=check)


def which(tool: str) -> bool:
    return subprocess.run(["which", tool], capture_output=True).returncode == 0


def check_dependencies() -> None:
    required = [
        "gdalbuildvrt", "gdal_calc.py", "gdalwarp",
        "gdaldem", "gdal2tiles.py", "gdal_translate",
        "gdaladdo", "gdalinfo",
    ]
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


def get_pixel_size(filename: str) -> float | None:
    """
    Retourne la taille de pixel X absolue (en unités du CRS) via gdalinfo.
    Retourne None si la lecture échoue.
    """
    result = subprocess.run(
        ["gdalinfo", filename],
        capture_output=True, text=True,
    )
    m = re.search(r"Pixel Size = \(([0-9.e+\-]+),", result.stdout)
    if m:
        return abs(float(m.group(1)))
    return None


def compute_oversample_factor(pixel_size_m: float, zoom_max: int) -> int:
    """
    Calcule le facteur de sur-échantillonnage (puissance de 2) pour que la
    résolution du raster colorisé soit proche de celle des tuiles au zoom
    cible, afin d'éviter la pixelisation aux forts zooms.

    La taille de pixel d'une tuile WebMercator (pseudo-mètres équatoriaux) :
        target = 2π × R_terre / (256 × 2^Z) ≈ 40 075 016 / (256 × 2^Z)

    On retourne la plus grande puissance de 2 ≤ (pixel_source / pixel_cible),
    bornée à MAX_OVERSAMPLE.  Retourne 1 si le ratio est inférieur au seuil.
    """
    target = 40_075_016.69 / (256 * 2 ** zoom_max)
    raw = pixel_size_m / target

    if raw <= OVERSAMPLE_THRESHOLD:
        return 1  # La résolution native est déjà adaptée

    # Puissance de 2 inférieure au ratio, bornée à MAX_OVERSAMPLE
    p = 1
    while p * 2 < raw and p < MAX_OVERSAMPLE:
        p *= 2
    return p


# ── Pipeline principal ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convertit les fichiers MNT LITTO3D (.asc) en MBTiles pour OpenCPN.\n"
            "L'effet de relief (hillshade multidirectionnel) est toujours activé."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_dir",
        help="Répertoire racine contenant les dossiers LITTO3D",
    )
    parser.add_argument(
        "output",
        help="Fichier de sortie .mbtiles",
    )
    parser.add_argument(
        "--resolution", default="1M", choices=["1M", "5M"],
        help="Résolution MNT à utiliser",
    )
    parser.add_argument(
        "--zoom-min", type=int, default=10,
        help="Niveau de zoom minimal",
    )
    parser.add_argument(
        "--zoom-max", type=int, default=18,
        help="Niveau de zoom maximal",
    )
    parser.add_argument(
        "--processes", type=int, default=8,
        help="Nombre de processus parallèles pour gdal2tiles",
    )
    parser.add_argument(
        "--resampling", default="bilinear",
        choices=["bilinear", "cubic", "lanczos", "cubicspline", "near", "average"],
        help="Méthode de rééchantillonnage (gdalwarp principal et gdal2tiles)",
    )
    parser.add_argument(
        "--keep-tmp", action="store_true",
        help="Conserver les fichiers temporaires (debug)",
    )
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
            vrt, *asc_files,
        ])

        # ── Étape 3 : Filtrage des valeurs NoData ──────────────────────────
        # Conserve toutes les valeurs valides (terre + bathymétrie) et remplace
        # les valeurs sentinelles LITTO3D (-99999) par le NoData interne.
        print("\n[3/6] Filtrage des valeurs NoData...")
        masked = os.path.join(tmpdir, "masked.tif")
        run([
            "gdal_calc.py",
            "-A", vrt,
            "--outfile", masked,
            "--calc", f"numpy.where(A > {NODATA_INTERNAL}, A, {NODATA_INTERNAL})",
            "--NoDataValue", str(NODATA_INTERNAL),
            "--type", "Float32",
            "--co", "COMPRESS=LZW",
            "--co", "TILED=YES",
            "--co", "BLOCKXSIZE=512",
            "--co", "BLOCKYSIZE=512",
            "--overwrite",
        ])

        # ── Étape 4 : Reprojection en Web Mercator ────────────────────────
        print(f"\n[4/6] Reprojection {INPUT_CRS} → {OUTPUT_CRS}...")
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

        # ── Étape 4b : Sur-échantillonnage adaptatif ──────────────────────
        # On sur-échantillonne le DEM Float32 *avant* la colorisation pour
        # deux raisons :
        #   1. Interpoler les profondeurs (float) plutôt que les couleurs
        #      (uint8) donne des dégradés fidèles aux frontières de couleurs.
        #   2. gdal2tiles n'a plus à upsampler massivement un raster BYTE,
        #      ce qui évite la pixelisation aux forts zooms.
        # On utilise cubicspline qui produit les transitions les plus douces
        # sans artefacts de repliement (ringing) pour ce type de données.
        src_pixel = get_pixel_size(reprojected)
        dem_for_color = reprojected  # défaut : pas de sur-échantillonnage

        if src_pixel is not None:
            print(f"\n  Taille de pixel source (WebMercator) : {src_pixel:.3f} m")
            factor = compute_oversample_factor(src_pixel, args.zoom_max)

            if factor > 1:
                new_pixel = src_pixel / factor
                print(
                    f"  → Sur-échantillonnage ×{factor} : "
                    f"{src_pixel:.3f} m → {new_pixel:.3f} m/pixel "
                    f"(zoom_max={args.zoom_max})"
                )
                oversampled = os.path.join(tmpdir, "oversampled.tif")
                run([
                    "gdalwarp",
                    "-r", "cubicspline",
                    "-tr", str(new_pixel), str(new_pixel),
                    "-srcnodata", str(NODATA_INTERNAL),
                    "-dstnodata", str(NODATA_INTERNAL),
                    "-co", "COMPRESS=LZW",
                    "-co", "TILED=YES",
                    "-co", "BLOCKXSIZE=512",
                    "-co", "BLOCKYSIZE=512",
                    reprojected, oversampled,
                ])
                dem_for_color = oversampled
            else:
                target_px = 40_075_016.69 / (256 * 2 ** args.zoom_max)
                print(
                    f"  → Résolution native suffisante "
                    f"(ratio {src_pixel / target_px:.1f}×), "
                    f"pas de sur-échantillonnage"
                )
        else:
            print("  ⚠  Impossible de lire la taille de pixel, pas de sur-échantillonnage")

        # ── Étape 5 : Colorisation + hillshade + fusion ────────────────────
        print("\n[5/6] Génération couleurs + relief ombré + fusion...")

        # 5a — Écriture de la table des couleurs
        color_file = os.path.join(tmpdir, "colors.txt")
        with open(color_file, "w") as fh:
            fh.write(COLOR_TABLE)

        # 5b — Dégradé de couleurs RGBA
        #   -alpha : ajoute un canal alpha ; les pixels NoData → alpha=0
        colored = os.path.join(tmpdir, "colored.tif")
        run([
            "gdaldem", "color-relief",
            dem_for_color, color_file, colored,
            "-alpha",
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
        ])

        # 5c — Hillshade multidirectionnel
        #
        #   -z HILLSHADE_Z_FACTOR
        #       Exagération verticale. Sans ça, les pentes douces de la
        #       bathymétrie SPM produisent un hillshade quasi-uniforme.
        #
        #   -multidirectional
        #       Éclairage depuis plusieurs azimuths : évite les zones
        #       entièrement dans l'ombre qu'un éclairage unique crée.
        #
        #   -compute_edges  ← CORRECTION PRINCIPALE DU BUG
        #       Sans cet argument, gdaldem laisse à NoData les pixels de
        #       bord du raster et les frontières entre tuiles ASC adjacentes.
        #       Lors de la fusion (étape 5d), ces pixels NoData sont traités
        #       comme 0 par gdal_calc.py → résultat = noir opaque → les
        #       « marches d'escalier » visibles dans OpenCPN.
        #       Avec -compute_edges, gdaldem utilise des noyaux Sobel partiels
        #       aux bords → valeur interpolée, aucun halo ni marche noire.
        hillshade = os.path.join(tmpdir, "hillshade.tif")
        run([
            "gdaldem", "hillshade",
            "-z", str(HILLSHADE_Z_FACTOR),
            "-multidirectional",
            "-compute_edges",
            dem_for_color, hillshade,
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
        ])

        # 5d — Fusion multiplicative (multiply blend) avec alpha préservé
        #
        #   Formule par canal RGB :
        #       out = clip( color_uint8 × hillshade_uint8 / 128 ,  0, 255 )
        #
        #   • hillshade = 128 → facteur 1.0  (neutre, couleur inchangée)
        #   • hillshade < 128 → assombrit    (versant ombragé)
        #   • hillshade > 128 → éclaircit    (versant exposé)
        #
        #   L'alpha est copié intact depuis colored.tif, ce qui garantit que :
        #   → les pixels NoData (alpha=0) restent transparents
        #   → AUCUNE marche d'escalier noire aux bords des tuiles ASC
        #
        #   Pourquoi gdal_calc.py et non « gdal raster blend --operator=hsv-value » ?
        #   L'opérateur HSV remplace entièrement le canal V par le hillshade et
        #   ne préserve pas le canal alpha correctement : les pixels transparents
        #   aux frontières de tuiles deviennent noirs (alpha=255), ce qui cause
        #   l'effet de marche d'escalier observé dans OpenCPN.
        #
        #   Attention : les arrays numpy A/B/C/E sont uint8 ici.
        #   uint8 × uint8 déborde silencieusement → cast explicite en float32
        #   avant multiplication, puis retour en uint8 après clipping.
        blended = os.path.join(tmpdir, "blended.tif")

        def rgb_calc(band_letter: str) -> str:
            return (
                f"numpy.clip("
                f"{band_letter}.astype(numpy.float32)"
                f" * E.astype(numpy.float32) / 128.0,"
                f" 0, 255"
                f").astype(numpy.uint8)"
            )

        run([
            "gdal_calc.py",
            "-A", colored,   "--A_band", "1",   # R couleur
            "-B", colored,   "--B_band", "2",   # G couleur
            "-C", colored,   "--C_band", "3",   # B couleur
            "-D", colored,   "--D_band", "4",   # Alpha (inchangé)
            "-E", hillshade, "--E_band", "1",   # Hillshade
            "--outfile", blended,
            "--calc", rgb_calc("A"),  # R fusionné
            "--calc", rgb_calc("B"),  # G fusionné
            "--calc", rgb_calc("C"),  # B fusionné
            "--calc", "D",            # Alpha inchangé
            "--type", "Byte",
            "--co", "COMPRESS=LZW",
            "--co", "TILED=YES",
            "--overwrite",
        ])

        # ── Étape 6 : Export MBTiles ───────────────────────────────────────
        print(
            f"\n[6/6] Génération des tuiles PNG → MBTiles "
            f"(zoom {args.zoom_min}–{args.zoom_max})..."
        )

        if os.path.exists(output_path):
            os.remove(output_path)

        if which("mb-util"):
            # ── Méthode A : gdal2tiles.py + mb-util (recommandée) ─────────
            tiles_dir = os.path.join(tmpdir, "tiles")
            run([
                "gdal2tiles.py",
                "--zoom",       f"{args.zoom_min}-{args.zoom_max}",
                "--processes",  str(args.processes),
                "--tiledriver", "PNG",
                "--resampling", args.resampling,
                "--webviewer",  "none",
                "--xyz",        # Schéma XYZ (standard OpenLayers / OpenCPN)
                blended, tiles_dir,
            ])
            run([
                "mb-util",
                "--image_format=png",
                "--scheme=xyz",   # Doit correspondre à --xyz ci-dessus
                tiles_dir, output_path,
            ])

        else:
            # ── Méthode B : driver MBTiles natif GDAL (fallback) ──────────
            print("  (Utilisation du driver MBTiles GDAL natif)")
            run([
                "gdal_translate",
                "-of", "MBTiles",
                "-co", "TILE_FORMAT=PNG",
                "-co", "ZOOM_LEVEL_STRATEGY=UPPER",
                blended, output_path,
            ])
            # Niveaux de zoom inférieurs via pyramide d'overviews
            factors = [2**i for i in range(1, args.zoom_max - args.zoom_min + 1)]
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
