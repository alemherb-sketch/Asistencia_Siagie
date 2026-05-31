# Usa una imagen base de Node.js
FROM node:20-bullseye

# Instalar Python y Tesseract OCR
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    tesseract-ocr \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- PYTHON SETUP ----
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar archivos principales
COPY *.py ./
COPY frontend/ ./frontend/

# ---- NEXT.JS SETUP ----
WORKDIR /app/admin-panel
COPY admin-panel/package.json ./
RUN npm install

# Copiar el panel
COPY admin-panel/ ./
# Construir Next.js
RUN npm run build

# ---- INICIO ----
WORKDIR /app
# Crear script para ejecutar ambos servidores
RUN echo '#!/bin/bash\n\
# Iniciar FastAPI en segundo plano en el puerto 8000\n\
uvicorn main:app --host 127.0.0.1 --port 8000 &\n\
\n\
# Iniciar Next.js en primer plano en el puerto provisto por Render\n\
cd admin-panel && npx next start -p ${PORT:-10000}\n\
' > /app/start-all.sh
RUN chmod +x /app/start-all.sh

EXPOSE 10000

CMD ["/app/start-all.sh"]
