from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from excel_processor import process_attendance
from upload_processor import process_uploads_logic, system_summary
from typing import List
import shutil
import tempfile
import glob
import re
import time

# Directorio base para subidas por partes (chunked). Cada sesión guarda sus
# archivos en disco hasta que se procesan todos juntos.
SESSIONS_DIR = os.path.join(tempfile.gettempdir(), "asistencia_sessions")


def _safe_session_dir(session_id, create=False):
    """Devuelve el directorio de la sesión, validando el id contra path traversal."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', session_id or ''):
        raise ValueError("session id inválido")
    d = os.path.join(SESSIONS_DIR, session_id)
    if create:
        os.makedirs(os.path.join(d, "siagie"), exist_ok=True)
        os.makedirs(os.path.join(d, "att"), exist_ok=True)
    return d


def _sweep_old_sessions(max_age_s=3600):
    """Borra sesiones abandonadas (más de 1h) para no llenar el disco."""
    try:
        now = time.time()
        if not os.path.isdir(SESSIONS_DIR):
            return
        for name in os.listdir(SESSIONS_DIR):
            p = os.path.join(SESSIONS_DIR, name)
            try:
                if os.path.isdir(p) and now - os.path.getmtime(p) > max_age_s:
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos del frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.exists(frontend_dir):
    os.makedirs(frontend_dir)

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.on_event("startup")
def _log_resources():
    print(f"[PERF] Recursos al iniciar: {system_summary()}")

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not found</h1>"

@app.get("/api/diag")
def diag():
    """Diagnóstico de recursos del contenedor. Confirma si el plan está
    limitado en CPU (la causa más común de que el paralelismo no acelere)."""
    return system_summary()

@app.get("/api/attendance")
def get_attendance(grado: str = Query("PRIMERO"), seccion: str = Query("A")):
    result = process_attendance(grado, seccion)
    return result

@app.post("/api/process_uploads")
async def process_uploads(
    siagie: List[UploadFile] = File(...),
    attendances: List[UploadFile] = File(...)
):
    import traceback
    try:
        # Crear directorio temporal para procesar los archivos
        with tempfile.TemporaryDirectory() as temp_dir:
            siagie_paths = []
            for s_file in siagie:
                s_path = os.path.join(temp_dir, s_file.filename)
                with open(s_path, "wb") as buffer:
                    shutil.copyfileobj(s_file.file, buffer)
                siagie_paths.append(s_path)
                
            att_paths = []
            for att_file in attendances:
                att_path = os.path.join(temp_dir, att_file.filename)
                with open(att_path, "wb") as buffer:
                    shutil.copyfileobj(att_file.file, buffer)
                att_paths.append(att_path)
                
            # Procesar usando la nueva lógica
            result = process_uploads_logic(siagie_paths, att_paths)
            return result
    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"[ERROR] process_uploads failed:\n{error_detail}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando archivos: {str(e)}", "detail": str(e)}
        )


@app.post("/api/upload_chunk")
async def upload_chunk(
    session: str = Form(...),
    kind: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """Recibe una tanda pequeña de archivos y los guarda en disco para la sesión.
    Evita la subida de los 118 archivos en una sola petición gigante."""
    try:
        _sweep_old_sessions()
        d = _safe_session_dir(session, create=True)
        sub = "siagie" if kind == "siagie" else "att"
        dest = os.path.join(d, sub)
        saved = 0
        for f in files:
            name = os.path.basename(f.filename or "")
            if not name:
                continue
            with open(os.path.join(dest, name), "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            saved += 1
        return {"ok": True, "saved": saved}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        import traceback
        print(f"[ERROR] upload_chunk failed:\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": f"Error subiendo archivos: {str(e)}"})


@app.post("/api/process_session")
async def process_session(session: str = Form(...)):
    """Procesa TODOS los archivos acumulados de la sesión (subidos por partes) y
    limpia la sesión. El resultado es idéntico al de una subida única."""
    import traceback
    try:
        d = _safe_session_dir(session, create=False)
        if not os.path.isdir(d):
            return JSONResponse(status_code=404, content={"error": "Sesión no encontrada o expirada. Vuelva a subir los archivos."})
        try:
            siagie_paths = sorted(glob.glob(os.path.join(d, "siagie", "*")))
            att_paths = sorted(glob.glob(os.path.join(d, "att", "*")))
            if not siagie_paths:
                return JSONResponse(status_code=400, content={"error": "No se recibió ningún PDF SIAGIE en la sesión."})
            result = process_uploads_logic(siagie_paths, att_paths)
            return result
        finally:
            shutil.rmtree(d, ignore_errors=True)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        print(f"[ERROR] process_session failed:\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando archivos: {str(e)}", "detail": str(e)}
        )
