import pandas as pd
import os
import glob
import re
import unicodedata

BASE_DIR = r"c:\Users\ALEM\Desktop\GESTION DE DATOS"
SIAGIE_DIR = os.path.join(BASE_DIR, "ARCHIVOS SIAGIE")
CUBICOL_DIR = os.path.join(BASE_DIR, "ARCHIVOS CUBICOL")

def normalize_name(name):
    if not isinstance(name, str):
        return ""
    # Remove accents
    name = ''.join(c for c in unicodedata.normalize('NFD', name)
                  if unicodedata.category(c) != 'Mn')
    name = name.upper()
    name = re.sub(r'[^A-Z, ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def get_siagie_file(grado, seccion):
    pattern = f"{grado} SECUNDARIA {seccion} SIAGIE.xlsx"
    path = os.path.join(SIAGIE_DIR, pattern)
    if os.path.exists(path):
        return path
    return None

def get_cubicol_file(grado, seccion):
    pattern = f"{grado} SECUNDARIA {seccion} CUBICOL.xls"
    path = os.path.join(CUBICOL_DIR, pattern)
    if os.path.exists(path):
        return path
    return None

def get_all_cubicol_files():
    return glob.glob(os.path.join(CUBICOL_DIR, "*CUBICOL.xls"))

def extract_siagie_names(filepath):
    df = pd.read_excel(filepath, header=None)
    names = []
    
    # We look for cells that look like "LASTNAME, FIRSTNAME"
    # Usually in column index 2 or 1.
    for _, row in df.iterrows():
        for val in row:
            if isinstance(val, str) and ',' in val:
                # Check if it looks like a name and not a long sentence
                parts = val.split(',')
                if len(parts) == 2 and len(val) < 60:
                    names.append(val.strip())
                    break # Move to next row
    
    return [normalize_name(n) for n in names if n], names

def parse_day_header(header):
    if not isinstance(header, str):
        return None
    # Solo considerar columnas que contengan la hora "7:45" o "08:00"
    if "7:45" not in header and "8:00" not in header:
        return None
    
    # e.g., "Viernes 29 [07:45]" -> num: "29", day: "V"
    # Uso [^\s\d]+ para atrapar palabras con tildes como "Miércoles"
    match = re.search(r'([^\s\d]+)\s+(\d+)', header)
    if match:
        day_str = match.group(1).upper()
        # Normalizar tildes para la inicial
        day_str = unicodedata.normalize('NFD', day_str).encode('ascii', 'ignore').decode('utf-8')
        num = match.group(2)
        initial = day_str[0]
        if day_str.startswith("MI"):
            initial = "X" # Miercoles
        return {"num": num, "day": initial, "full": header}
    return None

def map_attendance(val):
    if not isinstance(val, str):
        return ""
    val = val.strip().upper()
    mapping = {
        "P": ".",
        "FI": "F",
        "F": "F",
        "FJ": "J",
        "TI": "T",
        "T": "T",
        "TJ": "U",
        "U": "U",
        ".": "."
    }
    return mapping.get(val, val)

def process_attendance(grado, seccion):
    siagie_path = get_siagie_file(grado, seccion)
    if not siagie_path:
        return {"error": f"Archivo SIAGIE no encontrado para {grado} {seccion}"}
    
    norm_names, original_names = extract_siagie_names(siagie_path)
    if not norm_names:
        return {"error": "No se encontraron nombres en el archivo SIAGIE."}
    
    # We need to find each student in CUBICOL
    target_cubicol = get_cubicol_file(grado, seccion)
    all_cubicols = get_all_cubicol_files()
    
    # Prioritize target
    if target_cubicol in all_cubicols:
        all_cubicols.remove(target_cubicol)
        all_cubicols.insert(0, target_cubicol)
    
    # Cache to avoid reading the same file multiple times
    cubicol_cache = {}
    
    def get_cubicol_data(path):
        if path not in cubicol_cache:
            try:
                df = pd.read_excel(path, header=None)
                cubicol_cache[path] = df
            except:
                cubicol_cache[path] = None
        return cubicol_cache[path]

    # Pre-parse CUBICOL files
    parsed_cubicols = []
    for path in all_cubicols:
        df = get_cubicol_data(path)
        if df is None:
            continue
        
        # Find header row
        header_row_idx = -1
        days_cols = {} # col_idx -> parsed_day
        for idx, row in df.iterrows():
            for c_idx, val in enumerate(row):
                if isinstance(val, str) and "Dias" in val:
                    header_row_idx = idx
                    # Parse rest of this row for days
                    for dc_idx in range(c_idx + 1, len(row)):
                        parsed = parse_day_header(row[dc_idx])
                        if parsed:
                            days_cols[dc_idx] = parsed
                    break
            if header_row_idx != -1:
                break
        
        # Extract student rows
        students_data = {}
        if header_row_idx != -1:
            # We assume names are in the next rows, usually column 1 or 2
            # Let's just find the column named "Apellidos y Nombres" or scan rows
            for idx in range(header_row_idx + 1, len(df)):
                row = df.iloc[idx]
                for c_idx, val in enumerate(row):
                    if isinstance(val, str) and ',' in val:
                        n_name = normalize_name(val)
                        if len(n_name) > 5:
                            # Extract attendance for this student
                            att = {}
                            for dc_idx, d_info in days_cols.items():
                                cell_val = df.iloc[idx, dc_idx]
                                att[d_info['full']] = map_attendance(cell_val) if pd.notna(cell_val) else ""
                            students_data[n_name] = {
                                "attendance": att,
                                "days_cols": days_cols
                            }
                            break
        
        parsed_cubicols.append({"path": path, "students": students_data})

    # Read REPORTE GENERAL
    reporte_general = os.path.join(CUBICOL_DIR, "REPORTE GENERAL.xls")
    reporte_df = None
    if os.path.exists(reporte_general):
        try:
            reporte_df = pd.read_excel(reporte_general, header=None)
        except:
            pass

    def search_reporte_general(norm_name):
        if reporte_df is None:
            return "NO REPORTE"
        # Names are in row 5 headers: "Ap. Paterno", "Ap. Materno", "Nombres"
        # Or we can just concatenate strings in each row and match
        for idx, row in reporte_df.iterrows():
            # Skip first 5 rows usually
            if idx < 5: continue
            row_strs = [str(x) for x in row if pd.notna(x)]
            full_str = " ".join(row_strs)
            norm_full = normalize_name(full_str)
            # Simple match: if all parts of name are in norm_full
            parts = norm_name.replace(',', '').split()
            if all(p in norm_full for p in parts if len(p) > 2):
                # NGS is usually around column 9 or 10. Let's find "S1B" etc.
                # Just return the whole row as string for now, or find the NGS column.
                # In our inspection, NGS is column 9 (0-indexed).
                try:
                    return str(row[9])
                except:
                    return "ENCONTRADO PERO SIN NGS"
        return "NO ENCONTRADO"

    results = []
    not_found = []
    
    # We need a unified list of columns (days) for the table.
    # We will pick the days from the target cubicol file if available, or the first one that has days.
    all_days = []
    target_days = {}
    for pc in parsed_cubicols:
        if pc["path"] == target_cubicol and pc["students"]:
            # Get days from the first student
            first_student = list(pc["students"].values())[0]
            target_days = first_student["days_cols"]
            break
    
    if not target_days:
        for pc in parsed_cubicols:
            if pc["students"]:
                first_student = list(pc["students"].values())[0]
                target_days = first_student["days_cols"]
                break

    # Format days for frontend: Generate full month
    import datetime
    import calendar
    days_headers = []
    
    if target_days:
        # Find day 1 weekday
        first_known = list(target_days.values())[0]
        known_num = int(first_known["num"])
        known_day = first_known["day"]
        weekdays = ["L", "M", "X", "J", "V", "S", "D"]
        known_idx = weekdays.index(known_day)
        day1_idx = (known_idx - (known_num - 1)) % 7
        
        # Determine month and number of days
        target_path = target_cubicol if target_cubicol else all_cubicols[0]
        mtime = os.path.getmtime(target_path)
        dt = datetime.datetime.fromtimestamp(mtime)
        year, month = dt.year, dt.month
        
        # Test nearby months to find matching weekday for 1st of month
        found_num_days = 31 # default
        for m_offset in [0, -1, 1, -2, 2]:
            test_m = month + m_offset
            test_y = year
            if test_m < 1:
                test_m += 12
                test_y -= 1
            elif test_m > 12:
                test_m -= 12
                test_y += 1
            
            try:
                if datetime.date(test_y, test_m, 1).weekday() == day1_idx:
                    found_num_days = calendar.monthrange(test_y, test_m)[1]
                    break
            except:
                pass
        
        # Build mapping of num -> full header string
        cubicol_full_map = {}
        for d_info in target_days.values():
            cubicol_full_map[int(d_info["num"])] = d_info["full"]
            
        for i in range(1, found_num_days + 1):
            w_idx = (day1_idx + i - 1) % 7
            w_char = weekdays[w_idx]
            days_headers.append({
                "num": f"{i:02d}",
                "day": w_char,
                "full": cubicol_full_map.get(i, f"EMPTY_{i}")
            })

    for i, n_name in enumerate(norm_names):
        orig_name = original_names[i]
        found = False
        att_record = {}
        
        for pc in parsed_cubicols:
            # We try exact or close match
            for c_name, c_data in pc["students"].items():
                # Remove commas and check subset
                n_parts = n_name.replace(',', '').split()
                c_parts = c_name.replace(',', '').split()
                # If they share at least 2 words (e.g. 2 surnames)
                matches = sum(1 for p in n_parts if p in c_parts)
                if matches >= 2 or n_name == c_name:
                    found = True
                    att_record = c_data["attendance"]
                    break
            if found:
                break
        
        if found:
            row_data = {"name": orig_name, "attendance": []}
            for d in days_headers:
                row_data["attendance"].append(att_record.get(d["full"], ""))
            results.append(row_data)
        else:
            ngs_val = search_reporte_general(n_name)
            not_found.append({"name": orig_name, "ngs": ngs_val})
            
    return {
        "days": days_headers,
        "results": results,
        "not_found": not_found
    }

if __name__ == "__main__":
    res = process_attendance("PRIMERO", "A")
    print(res)
