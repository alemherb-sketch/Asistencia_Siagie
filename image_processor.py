"""
image_processor.py - Módulo OCR para leer imágenes de registros de asistencia.

Usa OpenCV para detección de cuadrícula y Tesseract OCR para lectura de texto.
Convierte imágenes de hojas de asistencia (fotos/capturas) a tablas estructuradas
que el sistema existente puede procesar.

Flujo:
  1. Preprocesar imagen (contraste, binarización, eliminación de ruido)
  2. Detectar líneas horizontales y verticales (cuadrícula)
  3. Extraer cada celda de la cuadrícula
  4. Clasificar cada celda (vacía, punto/presente, letra F/T/J/U, texto/nombre)
  5. Devolver tabla estructurada (lista de listas)
"""

import cv2
import numpy as np
import os
import re

# ─── Verificar dependencias opcionales ────────────────────────────────────────
try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


# ═══════════════════════════════════════════════════════════════════════════════
#  FUNCIONES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════

def check_ocr_available():
    """Verifica que Tesseract OCR esté instalado y disponible."""
    if not HAS_OCR:
        return False, "Librerías pytesseract/Pillow no instaladas. Ejecute: pip install pytesseract Pillow"
    try:
        pytesseract.get_tesseract_version()
        return True, "OK"
    except Exception:
        return False, (
            "Tesseract OCR no está instalado en el sistema. "
            "Windows: descargue de https://github.com/UB-Mannheim/tesseract/wiki | "
            "Linux: sudo apt-get install tesseract-ocr tesseract-ocr-spa"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  PREPROCESAMIENTO DE IMAGEN
# ═══════════════════════════════════════════════════════════════════════════════

def preprocess_image(image_path):
    """
    Carga y preprocesa la imagen para detección de cuadrícula y OCR.
    
    - Redimensiona si es muy grande
    - Convierte a escala de grises
    - Elimina ruido
    - Aplica binarización adaptativa
    
    Returns: (img_color, gray, binary_inverted)
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"No se pudo leer la imagen: {image_path}")

    # Redimensionar si es demasiado grande (rendimiento)
    max_dim = 3000
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Eliminar ruido preservando bordes
    denoised = cv2.fastNlMeansDenoising(gray, h=12, templateWindowSize=7, searchWindowSize=21)

    # Binarización adaptativa (invertida: tinta=blanco, fondo=negro)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=10
    )

    return img, gray, binary


# ═══════════════════════════════════════════════════════════════════════════════
#  DETECCIÓN DE CUADRÍCULA
# ═══════════════════════════════════════════════════════════════════════════════

def detect_lines(binary):
    """
    Detecta líneas horizontales y verticales usando operaciones morfológicas.
    Returns: (horizontal_mask, vertical_mask)
    """
    h, w = binary.shape

    # Líneas horizontales: kernel rectangular ancho
    h_len = max(w // 12, 40)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=2)

    # Líneas verticales: kernel rectangular alto
    v_len = max(h // 12, 40)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=2)

    return horizontal, vertical


def get_line_positions(mask, axis):
    """
    Obtiene coordenadas de las líneas desde una máscara.
    axis=1: suma por filas → obtiene posiciones Y (horizontales)
    axis=0: suma por columnas → obtiene posiciones X (verticales)
    
    Returns: lista de posiciones (enteros)
    """
    projection = np.sum(mask, axis=axis).astype(np.float64)
    threshold = np.max(projection) * 0.15 if np.max(projection) > 0 else 0

    positions = []
    in_line = False
    line_start = 0

    for i, val in enumerate(projection):
        if val > threshold:
            if not in_line:
                line_start = i
                in_line = True
        else:
            if in_line:
                positions.append((line_start + i) // 2)
                in_line = False
    if in_line:
        positions.append((line_start + len(projection)) // 2)

    # Eliminar duplicados (líneas muy cercanas)
    if len(positions) > 1:
        filtered = [positions[0]]
        min_gap = 8
        for p in positions[1:]:
            if p - filtered[-1] > min_gap:
                filtered.append(p)
        positions = filtered

    return positions


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTRACCIÓN Y CLASIFICACIÓN DE CELDAS
# ═══════════════════════════════════════════════════════════════════════════════

def extract_grid_cells(gray, h_positions, v_positions):
    """
    Extrae el contenido de cada celda usando las posiciones de la cuadrícula.
    
    Returns: tabla como lista de listas de strings
    """
    table = []
    margin = 4  # Margen en píxeles para evitar bordes de líneas

    for r in range(len(h_positions) - 1):
        row = []
        y1 = min(h_positions[r] + margin, gray.shape[0])
        y2 = max(h_positions[r + 1] - margin, 0)

        if y2 <= y1 or (y2 - y1) < 5:
            continue

        for c in range(len(v_positions) - 1):
            x1 = min(v_positions[c] + margin, gray.shape[1])
            x2 = max(v_positions[c + 1] - margin, 0)

            if x2 <= x1 or (x2 - x1) < 5:
                row.append("")
                continue

            cell = gray[y1:y2, x1:x2]
            cell_w = x2 - x1
            cell_h = y2 - y1
            text = classify_cell(cell, cell_w, cell_h)
            row.append(text)

        if row:
            table.append(row)

    return table


def classify_cell(cell_gray, cell_w, cell_h):
    """
    Clasifica el contenido de una celda individual.
    
    Estrategia basada en la proporción de píxeles oscuros y el ancho de la celda:
    - Muy poca tinta → vacía
    - Poca tinta en celda angosta → punto (presente ".")
    - Mucha tinta en celda angosta → letra (F, T, J, U) → OCR
    - Celda ancha → texto largo (nombre de alumno) → OCR
    - Celda con número → encabezado de día → OCR
    """
    if cell_gray.size == 0:
        return ""

    # Binarizar la celda con Otsu
    _, thresh = cv2.threshold(cell_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    dark_pixels = cv2.countNonZero(thresh)
    total = cell_gray.shape[0] * cell_gray.shape[1]
    ratio = dark_pixels / total if total > 0 else 0

    # ── Celda vacía ──
    if ratio < 0.008:
        return ""

    # ── Celda angosta con marca pequeña → punto (presente) ──
    if ratio < 0.12 and cell_w < 60 and cell_h < 60:
        return "."

    # ── Celda ancha → probablemente nombre de alumno ──
    if cell_w > 120:
        return _ocr_cell(cell_gray, psm=7, lang='spa')

    # ── Celda angosta con tinta → podría ser letra de asistencia o número ──
    if cell_w < 80:
        # psm=7 o psm=8 permite leer múltiples caracteres (ej: "12", "30") en lugar de forzar uno solo
        text = _ocr_cell(cell_gray, psm=8, whitelist='FTJUP.0123456789MLXVSDB')
        text = text.strip().upper() if text else ""

        # Letras de asistencia reconocidas
        if text in ['F', 'T', 'J', 'U']:
            return text
        if text in ['P', '.']:
            return '.'

        # Número (encabezado de día)
        clean = re.sub(r'[^0-9]', '', text)
        if clean and clean.isdigit():
            return clean

        # Letras de día de la semana
        if text in ['L', 'M', 'X', 'V', 'S', 'D']:
            return text

        # Si tiene tinta significativa pero no se reconoció → asumir presente
        if ratio > 0.04:
            return "."

        return text if text else ""

    # ── Celda mediana → intentar OCR general ──
    return _ocr_cell(cell_gray, psm=7, lang='spa')


def _ocr_cell(cell_gray, psm=10, whitelist=None, lang='spa'):
    """
    Aplica Tesseract OCR a una celda individual.
    
    psm: Page Segmentation Mode
      10 = caracter único
      7 = línea de texto única
    """
    if not HAS_OCR:
        return ""

    try:
        h, w = cell_gray.shape

        # Ampliar celdas pequeñas para mejor reconocimiento
        if w < 50 or h < 50:
            scale = max(50 / max(w, 1), 50 / max(h, 1), 2)
            cell_gray = cv2.resize(
                cell_gray, None,
                fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC
            )

        # Mejorar contraste con CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(cell_gray)

        pil_img = Image.fromarray(enhanced)

        config = f'--psm {psm} --oem 3'
        if whitelist:
            config += f' -c tessedit_char_whitelist={whitelist}'

        text = pytesseract.image_to_string(pil_img, lang=lang, config=config)
        return text.strip()
    except Exception as e:
        print(f"[OCR] Error en celda: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def image_to_table(image_path):
    """
    Función principal: convierte una imagen de asistencia en una tabla estructurada.
    
    La tabla resultante tiene el mismo formato que las tablas extraídas por
    pdfplumber o pandas (lista de listas de strings), por lo que puede ser
    procesada por las funciones existentes del sistema.
    
    Returns: lista de listas (tabla)
    Raises: RuntimeError si OCR no está disponible
    """
    available, msg = check_ocr_available()
    if not available:
        raise RuntimeError(f"OCR no disponible: {msg}")

    print(f"[OCR] Procesando imagen: {os.path.basename(image_path)}")

    # 1. Preprocesar
    img, gray, binary = preprocess_image(image_path)
    print(f"[OCR] Imagen: {gray.shape[1]}x{gray.shape[0]} px")

    # 2. Detectar cuadrícula
    h_mask, v_mask = detect_lines(binary)
    h_pos = get_line_positions(h_mask, axis=1)
    v_pos = get_line_positions(v_mask, axis=0)

    print(f"[OCR] Líneas detectadas: {len(h_pos)} horizontales, {len(v_pos)} verticales")

    if len(h_pos) < 3 or len(v_pos) < 3:
        # Cuadrícula no detectada → intentar OCR directo como respaldo
        print("[OCR] Cuadrícula insuficiente. Intentando OCR directo...")
        return _fallback_full_ocr(gray)

    # 3. Extraer celdas
    table = extract_grid_cells(gray, h_pos, v_pos)
    print(f"[OCR] Tabla extraída: {len(table)} filas x {max(len(r) for r in table) if table else 0} columnas")

    # 4. Limpiar filas vacías
    table = [row for row in table if any(cell.strip() for cell in row if cell)]

    return table


def _fallback_full_ocr(gray):
    """
    Respaldo: lee toda la imagen como texto sin detección de cuadrícula.
    Útil cuando la imagen no tiene líneas visibles.
    """
    if not HAS_OCR:
        return []

    try:
        pil_img = Image.fromarray(gray)
        text = pytesseract.image_to_string(pil_img, lang='spa', config='--psm 6')
        lines = text.strip().split('\n')
        table = []
        for line in lines:
            if line.strip():
                # Separar por espacios múltiples
                cells = re.split(r'\s{2,}', line.strip())
                table.append(cells)
        return table
    except Exception as e:
        print(f"[OCR] Error en OCR de respaldo: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERFAZ CON EL SISTEMA EXISTENTE
# ═══════════════════════════════════════════════════════════════════════════════

def parse_image_attendance(filepath, student_norms):
    """
    Parsea una imagen de asistencia y extrae datos de asistencia.
    
    Interfaz compatible con parse_generic_file() en upload_processor.py.
    Convierte la imagen en una tabla y luego la procesa con la lógica existente.
    
    Args:
        filepath: ruta a la imagen
        student_norms: lista de nombres normalizados de alumnos (SIAGIE)
    
    Returns: (att_data, extra_students) — mismo formato que parse_generic_file
    """
    try:
        table = image_to_table(filepath)
    except Exception as e:
        print(f"[OCR] Error procesando imagen {filepath}: {e}")
        return {}, []

    if not table:
        print(f"[OCR] No se extrajo ninguna tabla de {filepath}")
        return {}, []

    # Usar la lógica compartida de procesamiento de tablas
    from upload_processor import process_table_data
    return process_table_data(table, student_norms)
