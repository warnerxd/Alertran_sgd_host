"""
Convierte la imagen del logo a .ico para PyInstaller y la aplicacion.
Uso: python generar_icono.py <ruta_imagen>
     python generar_icono.py assets/alertran_icon.png
"""
import sys
from pathlib import Path
from PIL import Image

def convertir_a_ico(ruta_entrada: str):
    src = Path(ruta_entrada)
    if not src.exists():
        print(f"[ERROR] No se encontro: {src}")
        sys.exit(1)

    dst = Path("assets/alertran.ico")
    dst.parent.mkdir(exist_ok=True)

    img = Image.open(src).convert("RGBA")

    # Generar todos los tamaños estándar de Windows
    sizes = [16, 24, 32, 48, 64, 128, 256]
    iconos = []
    for s in sizes:
        resized = img.resize((s, s), Image.LANCZOS)
        iconos.append(resized)

    # Guardar como .ico multi-resolución
    iconos[0].save(
        dst,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=iconos[1:],
    )

    # También guardar PNG de 256px para uso en Qt
    png_dst = Path("assets/alertran_icon.png")
    img.resize((256, 256), Image.LANCZOS).save(png_dst, "PNG")

    print(f"[OK] ICO generado:  {dst}  ({dst.stat().st_size // 1024} KB)")
    print(f"[OK] PNG generado:  {png_dst}")
    print()
    print("Siguiente paso: reconstruir el ejecutable con   build.bat")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generar_icono.py <ruta_imagen>")
        print("Ejemplo: python generar_icono.py C:/Users/skate/Downloads/logo.png")
        sys.exit(1)
    convertir_a_ico(sys.argv[1])
