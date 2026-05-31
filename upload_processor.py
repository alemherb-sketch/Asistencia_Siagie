import pandas as pd
import pdfplumber
import re
import unicodedata
import os
import calendar
import datetime

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
    
    with pdfplumber.open(filepath) as pdf:
        current_seccion = "DESCONOCIDO"
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if not text: continue
            
            if nivel == "DESCONOCIDO":
                m = re.search(r'\b(INICIAL|PRIMARIA|SECUNDARIA)\b', text, re.IGNORECASE)
                if m: nivel = m.group(1).upper()
            
            if grado == "DESCONOCIDO":
                m = re.search(r'\b(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO)\b', text, re.IGNORECASE)
                if m: grado = m.group(1).upper()
                
            m_sec = re.search(r'(?:Secci[oó]n|Sec\.?)[\s:]*([A-Z])\b', text, re.IGNORECASE)
            if m_sec: 
                current_seccion = m_sec.group(1).upper()
            else:
                m2_sec = re.search(r'\b(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO)\s+([A-Z])\b', text, re.IGNORECASE)
                if m2_sec: current_seccion = m2_sec.group(2).upper()
                
            if not month_val:
                m = re.search(r'(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SETIEMBRE|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE).*?(\d{4})', text, re.IGNORECASE)
                if m:
                    month_val = get_month_number(m.group(1).upper())
                    year_val = int(m.group(2))
            
            lines = text.split('\n')
            for line in lines:
                m = re.search(r'^\s*\d+\s+([A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\s]+,\s*[A-ZÑÁÉÍÓÚ\s]+)', line)
                if m:
                    name = m.group(1).strip()
                    n_name = normalize_name(name)
                    if n_name and not any(s['norm'] == n_name for s in students):
                        students.append({'orig': name, 'norm': n_name, 'seccion': current_seccion})

    if not month_val:
        today = datetime.datetime.now()
        month_val = today.month
        year_val = today.year

    return {"nivel": nivel, "grado": grado, "month": month_val, "year": year_val, "students": students}

def map_attendance(val):
    if not isinstance(val, str): return ""
    val = val.strip().upper()
    mapping = {"P": ".", "FI": "F", "F": "F", "FJ": "J", "TI": "T", "T": "T", "TJ": "U", "U": "U", ".": "."}
    return mapping.get(val, val)

def parse_generic_file(filepath, ext, student_norms):
    att_data = {}
    extra_students = []
    
    def process_table(table):
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
            for r_idx in range(header_row_idx + 1, len(table)):
                row = table[r_idx]
                row_str = " ".join([str(c) for c in row if c])
                row_norm = normalize_name(row_str)
                
                if len(row_norm) < 10 or ',' not in row_str:
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
                    for s_norm in student_norms:
                        parts = s_norm.replace(',', '').split()
                        valid_parts = [p for p in parts if len(p) > 2]
                        if not valid_parts: continue
                        
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

    if ext == '.pdf':
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    process_table(table)
    else:
        try:
            df = pd.read_excel(filepath, header=None)
            table = df.fillna("").values.tolist()
            process_table(table)
        except Exception as e:
            print(f"Error reading excel {filepath}: {e}")
            
    return att_data, extra_students

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

def process_uploads_logic(siagie_paths, att_paths):
    all_students = []
    student_norms = []
    
    global_month = None
    global_year = None
    
    niveles = set()
    grados = set()
    secciones = set()
    
    for s_path in siagie_paths:
        s_info = extract_siagie_pdf(s_path)
        
        n = s_info.get("nivel", "DESCONOCIDO")
        g = s_info.get("grado", "DESCONOCIDO")
        
        if n != "DESCONOCIDO": niveles.add(n)
        if g != "DESCONOCIDO": grados.add(g)
        
        if not global_month and s_info["month"]:
            global_month = s_info["month"]
            global_year = s_info["year"]
            
        for student in s_info["students"]:
            sec = student.get("seccion", "DESCONOCIDO")
            if sec != "DESCONOCIDO": secciones.add(sec)
            
            student["nivel"] = n
            student["grado"] = g
            all_students.append(student)
            student_norms.append(student['norm'])
            
    if not global_month:
        import datetime
        today = datetime.datetime.now()
        global_month = today.month
        global_year = today.year
    
    all_att_data = {}
    all_extra_students = []
    
    for att_path in att_paths:
        ext = os.path.splitext(att_path)[1].lower()
        if ext in ['.pdf', '.xls', '.xlsx']:
            att_data, extra_students = parse_generic_file(att_path, ext, student_norms)
            for s_norm, data in att_data.items():
                if s_norm not in all_att_data:
                    all_att_data[s_norm] = {}
                all_att_data[s_norm].update(data)
                
            for ex in extra_students:
                if not any(s['name'] == ex['name'] for s in all_extra_students):
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
            
    return {
        "nivel": ", ".join(sorted(list(niveles))) if niveles else "DESCONOCIDO",
        "grado": ", ".join(sorted(list(grados))) if grados else "DESCONOCIDO",
        "seccion": ", ".join(sorted(list(secciones))) if secciones else "DESCONOCIDO",
        "days": days_headers,
        "results": results,
        "not_found": not_found,
        "extra_students": all_extra_students
    }
