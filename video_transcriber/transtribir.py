"""Punto de entrada compatible con el script original.

Mantiene el nombre del archivo para no romper hábitos previos, pero delega
la lógica al mini proyecto `transcriber`.
"""

from transcriber.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
