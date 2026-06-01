from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from excel_processor import process_attendance
from upload_processor import process_uploads_logic
from typing import List
import shutil
import tempfile

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

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not found</h1>"

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
