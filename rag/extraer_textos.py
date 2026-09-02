"""
Extrae texto limpio desde los documentos normativos descargados (XML de LeyChile/BCN y PDFs)
y los guarda como .txt planos, listos para trocear e indexar en el RAG.
"""
import html
import re
from pathlib import Path

from pypdf import PdfReader

CARPETA = Path(__file__).parent
CARPETA_RAW = CARPETA / "raw"
CARPETA_CORPUS = CARPETA / "corpus"


def limpiar_xml_leychile(ruta_xml, ruta_txt_salida, titulo):
    contenido = Path(ruta_xml).read_text(encoding="utf-8")
    # Extrae todo el contenido de las etiquetas <Texto>...</Texto>
    bloques = re.findall(r"<Texto>(.*?)</Texto>", contenido, flags=re.DOTALL)
    partes = [titulo, ""]
    for bloque in bloques:
        texto = html.unescape(bloque)
        texto = re.sub(r"[ \t]+", " ", texto)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        partes.append(texto.strip())
        partes.append("")
    Path(ruta_txt_salida).write_text("\n".join(partes), encoding="utf-8")
    print(f"{ruta_txt_salida.name}: {len(bloques)} bloques de texto extraidos")


def extraer_pdf(ruta_pdf, ruta_txt_salida, titulo):
    reader = PdfReader(str(ruta_pdf))
    partes = [titulo, ""]
    for i, page in enumerate(reader.pages):
        texto = page.extract_text() or ""
        texto = re.sub(r"[ \t]+", " ", texto)
        partes.append(f"--- Página {i + 1} ---")
        partes.append(texto.strip())
        partes.append("")
    Path(ruta_txt_salida).write_text("\n".join(partes), encoding="utf-8")
    print(f"{ruta_txt_salida.name}: {len(reader.pages)} páginas extraídas")


if __name__ == "__main__":
    # Nota: la copia consolidada completa del RSA (decreto13.xml, ~24k líneas) se descartó del
    # corpus final porque el endpoint obtxml de BCN incrusta bloques binarios (adjuntos en base64)
    # ajenos al articulado y porque las tablas de límites numéricos no vienen como texto plano ahí.
    # Se usa en su lugar el propio texto del decreto (más acotado) y la guía MINSAL, que sí trae
    # los valores de las tablas.
    limpiar_xml_leychile(
        CARPETA_RAW / "ley_20606.xml",
        CARPETA_CORPUS / "01_ley_20606.txt",
        "LEY N° 20.606 - SOBRE COMPOSICIÓN NUTRICIONAL DE LOS ALIMENTOS Y SU PUBLICIDAD "
        "(Fuente: Biblioteca del Congreso Nacional, www.bcn.cl/leychile, idNorma=1041570)",
    )
    extraer_pdf(
        CARPETA_RAW / "decreto13_faolex.pdf",
        CARPETA_CORPUS / "02_decreto13_rsa_sellos.txt",
        "DECRETO 13 DE 2015, MINISTERIO DE SALUD - MODIFICA EL REGLAMENTO SANITARIO DE LOS "
        "ALIMENTOS (D.S. 977/1996): SELLOS 'ALTO EN', LÍMITES NUTRICIONALES Y PROHIBICIÓN DE "
        "VENTA/PUBLICIDAD EN ESTABLECIMIENTOS EDUCACIONALES "
        "(Fuente: faolex.fao.org/docs/pdf/chi155737.pdf, copia del decreto publicado por BCN)",
    )
    extraer_pdf(
        CARPETA_RAW / "guia_kioscos.pdf",
        CARPETA_CORPUS / "03_guia_kioscos_saludables.txt",
        "GUÍA DE KIOSCOS Y COLACIONES SALUDABLES - MINISTERIO DE SALUD DE CHILE "
        "(Fuente: www.minsal.cl/wp-content/uploads/2016/05/GUIA-DE-KIOSCOS-SALUDABLES.pdf)",
    )
