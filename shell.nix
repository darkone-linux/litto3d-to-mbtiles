{
  pkgs ? import <nixpkgs> { },
}:

pkgs.mkShell {
  buildInputs = with pkgs; [

    # GDAL et outils géospatiaux
    gdal
    proj

    # Outils de tuiles
    mbutil

    # Base de données
    sqlite

    # Python
    python3

    # Outils de débogage
    #qgis

    # Utilitaires
    git
    wget
    curl
    p7zip
  ];

  shellHook = ''
    echo "Usage:"
    echo "python3 litto3d_to_mbtiles.py <litto3d_dir> <output.mbtiles> [options]"
    echo "python3 update-mbtiles.py <source_dir> <output_dir>"
  '';
}
