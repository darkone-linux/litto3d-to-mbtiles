{
  pkgs ? import <nixpkgs> { },
}:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # GDAL et outils géospatiaux
    gdal
    proj
    geos
    libgeotiff

    # Mapnik
    mapnik

    # Outils de tuiles
    mbutil

    # Base de données
    sqlite

    # Python
    python3
    python3Packages.fiona
    python3Packages.shapely
    python3Packages.pillow

    # Outils de débogage
    qgis

    # Utilitaires
    git
    wget
    curl
  ];

  shellHook = ''
    echo "OK"
  '';
}
