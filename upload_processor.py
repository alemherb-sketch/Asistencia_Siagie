import pandas as pd
import pdfplumber
import re
import unicodedata
import os
import calendar
import datetime
import multiprocessing as mp

def normalize_name(name):
    if not isinstance(name, str): return ""
    name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    name = name.upper()
    name = re.sub(r'[^A-Z, ]', '', name)
    return re.sub(r'\s+', ' ', name).strip()

def get_month_number(month_name):
    months = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
        "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
        "SETIEMBRE": 9, "SEPTIEMBRE": 9, "OCTUBRE": 10,
        "NOVIEMBRE": 11, "DICIEMBRE": 12
    }
    return months.get(month_name, None)

def extract_siagie_pdf(filepath):
    nivel, grado = "DESCONOCIDO", "DESCONOCIDO"
    month_val, year_val = None, None
    students = []

    MONTH_PATTERN = r'(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SETIEMBRE|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)'

    with pdfplumber.open(filepath) as pdf:
        current_seccion = "DESCONOCIDO"
        detected_month_name = None  # mes encontrado sin año cercano
        detected_year = None        # año encontrado en cualquier página

        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if not text:
                continue

            if nivel == "DESCONOCIDO":
                m = re.search(r'\b(INICIAL|PRIMARIA|SECUNDARIA)\b', text, re.IGNORECASE)
                if m: nivel = m.group(1).upper()

            if grado == "DESCONOCIDO":
                m = re.search(r'\b(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|\d+\s*AÑOS?)\b', text, re.IGNORECASE)
                if m: grado = m.group(1).upper()

            m_sec = re.search(r'(?:Secci[oó]n|Sec\.?)[\s:]*([A-Z])\b', text, re.IGNORECASE)
            if m_sec:
                current_seccion = m_sec.group(1).upper()
            else:
                m2_sec = re.search(r'\b(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|\d+\s*AÑOS?)\s+([A-Z])\b', text, re.IGNORECASE)
                if m2_sec: current_seccion = m2_sec.group(2).upper()

            # Buscar mes/año por página (evita acumular texto de todo el PDF)
            if not month_val:
                # Intento 1: mes y año en la misma página
                m = re.search(MONTH_PATTERN + r'[\s\S]{0,60}?(\d{4})', text, re.IGNORECASE)
                if m:
                    month_val = get_month_number(m.group(1).upper())
                    year_val = int(m.group(2))
                else:
                    # Intento 2: mes y año por separado en esta página
                    m_month = re.search(MONTH_PATTERN, text, re.IGNORECASE)
                    m_year = re.search(r'\b(20[2-3]\d)\b', text)
                    if m_month and m_year:
                        month_val = get_month_number(m_month.group(1).upper())
                        year_val = int(m_year.group(1))
                        print(f"[SIAGIE] Mes detectado (separado): {m_month.group(1)} {year_val}")
                    elif m_month:
                        detected_month_name = m_month.group(1).upper()
                    if m_year and not detected_year:
                        detected_year = int(m_year.group(1))

                    # Intento 3: formato numérico (ej: "Mes: 05")
                    if not month_val:
                        m_num = re.search(r'(?:Mes|Periodo|Período|MES)[\s:]*(\d{1,2})(?:[/\-\s]+(\d{4}))?', text, re.IGNORECASE)
                        if m_num:
                            month_num = int(m_num.group(1))
                            if 1 <= month_num <= 12:
                                month_val = month_num
                                year_val = int(m_num.group(2)) if m_num.group(2) else detected_year
                                print(f"[SIAGIE] Mes detectado (numérico): {month_val} {year_val}")
            elif not detected_year:
                m_year = re.search(r'\b(20[2-3]\d)\b', text)
                if m_year:
                    detected_year = int(m_year.group(1))
                    if not year_val:
                        year_val = detected_year

            lines = text.split('\n')
            for line in lines:
                m = re.search(r'^\s*\d+\s+([A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\s]+,\s*[A-ZÑÁÉÍÓÚ\s]+)', line)
                if m:
                    name = m.group(1).strip()
                    n_name = normalize_name(name)
                    if n_name and not any(s['norm'] == n_name for s in students):
                        students.append({'orig': name, 'norm': n_name, 'seccion': current_seccion})

    # Combinar mes/año detectados en distintas páginas
    if not month_val and detected_month_name:
        month_val = get_month_number(detected_month_name)
        year_val = detected_year

    if month_val and not year_val:
        year_val = detected_year or datetime.datetime.now().year

    if not month_val:
        utc_now = datetime.datetime.utcnow()
        peru_now = utc_now + datetime.timedelta(hours=-5)
        month_val = peru_now.month
        year_val = peru_now.year
        print(f"[SIAGIE] ADVERTENCIA: No se detectó mes en {os.path.basename(filepath)}. Usando mes actual (Perú): {month_val}/{year_val}")

    return {"nivel": nivel, "grado": grado, "month": month_val, "year": year_val, "students": students}

def map_attendance(val):
    if not isinstance(val, str): return ""
    val = val.strip().upper()
    mapping = {"P": ".", "FI": "F", "F": "F", "FJ": "J", "TI": "T", "T": "T", "TJ": "U", "U": "U", ".": "."}
    return mapping.get(val, val)

def process_table_data(table, student_norms):
    """
    Procesa una tabla (lista de listas) y extrae datos de asistencia.
    Función independiente reutilizable por parse_generic_file e image_processor.
    
    Returns: (att_data, extra_students)
    """
    att_data = {}
    extra_students = []
    
    header_row_idx = -1
    day_cols = {}
    for r_idx, row in enumerate(table):
        nums_found = 0
        temp_cols = {}
        for c_idx, cell in enumerate(row):
            cell_str = str(cell).strip() if cell is not None else ""
            m = re.search(r'\b(0?[1-9]|[12]\d|3[01])\b', cell_str)
            if m:
                m_time = re.search(r'(\d{1,2}):(\d{2})', cell_str)
                if m_time:
                    hour = int(m_time.group(1))
                    if hour >= 12:
                        continue
                        
                day = m.group(1).zfill(2)
                temp_cols[c_idx] = day
                nums_found += 1
        if nums_found >= 5:
            header_row_idx = r_idx
            day_cols = temp_cols
            break
            
    if header_row_idx != -1:
        # Precomputar las partes válidas de cada nombre UNA sola vez (en vez de
        # recalcular .replace().split() por cada fila × cada alumno).
        student_parts = []
        for s_norm in student_norms:
            valid_parts = [p for p in s_norm.replace(',', '').split() if len(p) > 2]
            if valid_parts:
                student_parts.append((s_norm, valid_parts))

        for r_idx in range(header_row_idx + 1, len(table)):
            row = table[r_idx]
            row_str = " ".join([str(c) for c in row if c])
            row_norm = normalize_name(row_str)

            if len(row_norm) < 10:
                continue # Saltar filas que no parecen nombres

            best_match = None

            # Pasada 1: Coincidencia exacta
            for s_norm in student_norms:
                if s_norm in row_norm:
                    best_match = s_norm
                    break

            # Pasada 2: Coincidencia parcial (fuzzy) al mejor postor
            if not best_match:
                best_score = 0
                for s_norm, valid_parts in student_parts:
                    matches = sum(1 for p in valid_parts if p in row_norm)
                    score = matches / len(valid_parts)

                    # Exigir al menos 2 coincidencias y un score > 0.5
                    if matches >= 2 and score > 0.5 and score > best_score:
                        best_score = score
                        best_match = s_norm
                        
            if best_match:
                s_norm = best_match
                if s_norm not in att_data:
                    att_data[s_norm] = {}
                for c_idx, day_str in day_cols.items():
                    if c_idx < len(row):
                        val = row[c_idx]
                        if val:
                            att_data[s_norm][day_str] = map_attendance(str(val))
                    
            else:
                # Verificar si la fila tiene alguna marca de asistencia
                has_att = False
                for c_idx in day_cols:
                    if c_idx < len(row) and row[c_idx]:
                        mapped = map_attendance(str(row[c_idx]))
                        if mapped in ['.', 'F', 'T', 'J', 'U']:
                            has_att = True
                            break
                
                if has_att:
                    m_name = re.search(r'([A-ZÑÁÉÍÓÚ]+[A-ZÑÁÉÍÓÚ\s]*,\s*[A-ZÑÁÉÍÓÚ\s]+)', row_str.upper())
                    extra_name = m_name.group(1).strip() if m_name else row_str.strip()
                    if not any(s['name'] == extra_name for s in extra_students):
                        extra_students.append({"name": extra_name, "ngs": "EN ASISTENCIA, NO EN SIAGIE"})

    return att_data, extra_students


IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')


def parse_generic_file(filepath, ext, student_norms):
    """Parsea un archivo de asistencia (PDF, Excel o Imagen) y extrae datos."""
    tables = []
    
    if ext == '.pdf':
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables_extracted = page.extract_tables()
                if not tables_extracted:
                    # Fallback para PDFs sin bordes de tabla definidos (exportados de Excel)
                    tables_extracted = page.extract_tables(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
                for table in tables_extracted:
                    tables.append(table)
    elif ext in IMAGE_EXTENSIONS:
        try:
            from image_processor import image_to_table
            table = image_to_table(filepath)
            if table:
                tables.append(table)
        except ImportError:
            raise RuntimeError("Faltan librerías para leer imágenes (pytesseract, Pillow). Ejecute pip install pytesseract Pillow")
        except Exception as e:
            raise RuntimeError(f"Error procesando imagen: {str(e)}")
    else:
        try:
            df = pd.read_excel(filepath, header=None)
            table = df.fillna("").values.tolist()
            tables.append(table)
        except Exception as e:
            print(f"Error reading excel {filepath}: {e}")
    
    # Procesar todas las tablas y fusionar resultados
    all_att_data = {}
    all_extra = []
    
    for table in tables:
        att_data, extra = process_table_data(table, student_norms)
        for key, val in att_data.items():
            if key not in all_att_data:
                all_att_data[key] = {}
            all_att_data[key].update(val)
        for ex in extra:
            if not any(s['name'] == ex['name'] for s in all_extra):
                all_extra.append(ex)
    
    return all_att_data, all_extra

def generate_month_days(year, month):
    weekdays = ["L", "M", "X", "J", "V", "S", "D"]
    num_days = calendar.monthrange(year, month)[1]
    
    days = []
    for i in range(1, num_days + 1):
        dt = datetime.date(year, month, i)
        w_char = weekdays[dt.weekday()]
        days.append({
            "num": f"{i:02d}",
            "day": w_char,
            "full": f"{i:02d}"
        })
    return days

# ═══════════════════════════════════════════════════════════════════════════════
#  PROCESAMIENTO EN PARALELO
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_workers(n_items):
    """
    Número de procesos a usar. Configurable con la variable de entorno MAX_WORKERS
    (útil en Render para ajustar según la RAM/CPU del plan contratado).
    Por defecto usa los núcleos disponibles, con tope de 4 para no exceder memoria.
    """
    env = os.environ.get("MAX_WORKERS", "").strip()
    if env:
        try:
            n = int(env)
            if n > 0:
                return min(n, n_items)
        except ValueError:
            pass
    cpu = os.cpu_count() or 2
    return max(1, min(cpu, 4, n_items))


def _siagie_worker(path):
    """Worker de proceso: extrae datos de un PDF SIAGIE. Tolerante a fallos por archivo."""
    try:
        return extract_siagie_pdf(path)
    except Exception as e:
        print(f"[SIAGIE] Error procesando {os.path.basename(path)}: {e}")
        return {"nivel": "DESCONOCIDO", "grado": "DESCONOCIDO",
                "month": None, "year": None, "students": []}


def _attendance_worker(args):
    """Worker de proceso: parsea un archivo de asistencia. Tolerante a fallos por archivo."""
    path, student_norms = args
    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.pdf', '.xls', '.xlsx') and ext not in IMAGE_EXTENSIONS:
        return {}, []
    try:
        return parse_generic_file(path, ext, student_norms)
    except Exception as e:
        print(f"[ATT] Error procesando {os.path.basename(path)}: {e}")
        return {}, []


def _run_parallel(func, items):
    """
    Ejecuta `func` sobre `items` repartiendo el trabajo entre varios procesos.
    Preserva el orden de entrada (resultados idénticos al modo secuencial).
    maxtasksperchild recicla los procesos para liberar memoria periódicamente
    (reemplaza el viejo gc.collect()/malloc_trim por archivo).
    Si el pool no está disponible, cae a modo secuencial.
    """
    n = len(items)
    if n == 0:
        return []
    workers = _resolve_workers(n)
    if workers <= 1 or n == 1:
        return [func(it) for it in items]
    try:
        with mp.Pool(processes=workers, maxtasksperchild=3) as pool:
            return pool.map(func, items)
    except Exception as e:
        print(f"[PARALLEL] Pool no disponible ({e}); usando modo secuencial")
        return [func(it) for it in items]


def process_uploads_logic(siagie_paths, att_paths):
    all_students = []
    student_norms = []
    
    global_month = None
    global_year = None
    
    niveles = set()
    grados = set()
    secciones = set()
    
    # Fase 1: extraer todos los PDFs SIAGIE en paralelo (map preserva el orden,
    # por lo que el resultado es idéntico al procesamiento secuencial).
    siagie_results = _run_parallel(_siagie_worker, siagie_paths)
    for s_info in siagie_results:
        n = s_info.get("nivel", "DESCONOCIDO")
        g = s_info.get("grado", "DESCONOCIDO")

        if n != "DESCONOCIDO": niveles.add(n)
        if g != "DESCONOCIDO": grados.add(g)

        if not global_month and s_info.get("month"):
            global_month = s_info["month"]
            global_year = s_info["year"]
            print(f"[PROCESS] Mes/Año detectado del SIAGIE: {global_month}/{global_year}")

        for student in s_info.get("students", []):
            sec = student.get("seccion", "DESCONOCIDO")
            if sec != "DESCONOCIDO": secciones.add(sec)

            student["nivel"] = n
            student["grado"] = g
            all_students.append(student)
            student_norms.append(student['norm'])

    if not global_month:
        # Fallback: usar hora de Perú (UTC-5)
        utc_now = datetime.datetime.utcnow()
        peru_offset = datetime.timedelta(hours=-5)
        peru_now = utc_now + peru_offset
        global_month = peru_now.month
        global_year = peru_now.year
        print(f"[PROCESS] ADVERTENCIA: Usando mes actual (Perú): {global_month}/{global_year}")
    
    all_att_data = {}
    all_extra_students = []
    seen_extra = set()

    # Fase 2: parsear todos los archivos de asistencia en paralelo.
    att_args = [(p, student_norms) for p in att_paths]
    att_results = _run_parallel(_attendance_worker, att_args)
    for att_data, extra_students in att_results:
        for s_norm, data in att_data.items():
            if s_norm not in all_att_data:
                all_att_data[s_norm] = {}
            all_att_data[s_norm].update(data)

        for ex in extra_students:
            if ex['name'] not in seen_extra:
                seen_extra.add(ex['name'])
                all_extra_students.append(ex)

    days_headers = generate_month_days(global_year, global_month)
    
    results = []
    not_found = []
    
    for s in all_students:
        norm = s['norm']
        if norm in all_att_data:
            row = {
                "name": s['orig'], 
                "attendance": [],
                "nivel": s['nivel'],
                "grado": s['grado'],
                "seccion": s['seccion']
            }
            for d in days_headers:
                row["attendance"].append(all_att_data[norm].get(d["num"], ""))
            results.append(row)
        else:
            not_found.append({
                "name": s['orig'], 
                "ngs": "SIN REGISTRO EN ASISTENCIA",
                "nivel": s['nivel'],
                "grado": s['grado'],
                "seccion": s['seccion']
            })
            
    # Nombres de meses en español
    MONTH_NAMES = {
        1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
        5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
        9: "SETIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
    }
    
    return {
        "nivel": ", ".join(sorted(list(niveles))) if niveles else "DESCONOCIDO",
        "grado": ", ".join(sorted(list(grados))) if grados else "DESCONOCIDO",
        "seccion": ", ".join(sorted(list(secciones))) if secciones else "DESCONOCIDO",
        "month": global_month,
        "year": global_year,
        "month_name": MONTH_NAMES.get(global_month, "DESCONOCIDO"),
        "days": days_headers,
        "results": results,
        "not_found": not_found,
        "extra_students": all_extra_students
    }
