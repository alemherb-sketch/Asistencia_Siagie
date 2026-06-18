document.addEventListener("DOMContentLoaded", () => {
    const btnSearch = document.getElementById("btn-search");
    const loader = document.getElementById("loader");
    const errorMessage = document.getElementById("error-message");
    const attendanceTable = document.getElementById("attendance-table");
    const tableHeader = document.getElementById("table-header");
    const tableBody = document.getElementById("table-body");
    const tableFooterRow = document.getElementById("table-footer-row");
    
    const notFoundContainer = document.getElementById("not-found-container");
    const notFoundBody = document.getElementById("not-found-body");
    
    const summaryContainer = document.getElementById("summary-container");
    const totalStudentsSpan = document.getElementById("total-students");
    const studentDetailsSpan = document.getElementById("student-details");

    const btnProcess = document.getElementById("btn-process");
    const siagieInput = document.getElementById("siagie-file");
    const attInput = document.getElementById("att-files");
    const detectedGradeSpan = document.getElementById("detected-grade");

    let globalData = null;

    btnProcess.addEventListener("click", processUploads);

    const nivelFilter = document.getElementById("nivel-filter");
    const gradoFilter = document.getElementById("grado-filter");
    const seccionFilter = document.getElementById("seccion-filter");

    [nivelFilter, gradoFilter, seccionFilter].forEach(el => {
        el.addEventListener("change", applyFilters);
    });

    async function processUploads() {
        if (siagieInput.files.length === 0) {
            showError("Por favor, seleccione el/los PDF de SIAGIE primero.");
            return;
        }

        if (attInput.files.length === 0) {
            showError("Por favor, seleccione al menos un archivo de asistencias (Excel o PDF).");
            return;
        }

        // Reset UI
        errorMessage.classList.add("hidden");
        attendanceTable.classList.add("hidden");
        notFoundContainer.classList.add("hidden");
        summaryContainer.classList.add("hidden");
        document.getElementById("filters-container").style.display = "none";
        loader.classList.remove("hidden");

        const nSiagie = siagieInput.files.length;
        const nAtt = attInput.files.length;
        let elapsed = 0;
        loader.textContent = `Procesando ${nSiagie} PDF(s) SIAGIE + ${nAtt} archivo(s) de asistencia...`;

        const timerInterval = setInterval(() => {
            elapsed++;
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
            if (elapsed < 30) {
                loader.textContent = `Procesando ${nSiagie} PDF(s) SIAGIE + ${nAtt} archivo(s)... (${timeStr})`;
            } else if (elapsed < 90) {
                loader.textContent = `Analizando y cruzando datos... (${timeStr})\nEsto puede tomar varios minutos con muchos archivos.`;
            } else {
                loader.textContent = `Aún procesando... (${timeStr}) — por favor espere, no cierre la página.`;
            }
        }, 1000);

        const controller = new AbortController();
        const abortTimeout = setTimeout(() => controller.abort(), 25 * 60 * 1000);

        try {
            const formData = new FormData();

            for (let i = 0; i < siagieInput.files.length; i++) {
                formData.append("siagie", siagieInput.files[i]);
            }

            for (let i = 0; i < attInput.files.length; i++) {
                formData.append("attendances", attInput.files[i]);
            }

            const response = await fetch('/asistencia/api/process_uploads', {
                method: 'POST',
                body: formData,
                signal: controller.signal
            });
            
            if (!response.ok) {
                let errorText;
                try {
                    const errData = await response.json();
                    errorText = errData.detail || errData.error || JSON.stringify(errData);
                } catch {
                    errorText = await response.text();
                    // Si recibimos HTML (probable redirect del middleware), indicarlo
                    if (errorText.includes('<!DOCTYPE') || errorText.includes('<html')) {
                        errorText = `Error ${response.status}: La sesión puede haber expirado. Recargue la página e inicie sesión nuevamente.`;
                    }
                }
                showError("Error en el servidor: " + errorText);
                return;
            }
            
            const data = await response.json();
            
            if (data.error) {
                showError(data.error);
                return;
            }

            globalData = data;
            populateFilters(data);
            
            // Render detected grade overall
            const nivelText = data.nivel && data.nivel !== "DESCONOCIDO" ? `Nivel: ${data.nivel} | ` : "";
            const monthText = data.month_name ? ` | Mes: ${data.month_name} ${data.year}` : "";
            detectedGradeSpan.textContent = `${nivelText}Grado: ${data.grado} | Sección: ${data.seccion}${monthText}`;
            
            applyFilters();
            
        } catch (err) {
            if (err.name === 'AbortError') {
                showError(`Tardó más de 25 minutos. La mayor parte es la SUBIDA de los archivos a internet, no el procesamiento. Suba menos archivos a la vez (por ejemplo, un grado a la vez) o use una conexión más rápida.`);
            } else if (err.name === 'TypeError') {
                showError(`Error de conexión: el servidor no respondió (${err.message}). El servidor puede estar iniciando — espere 30 segundos y reintente.`);
            } else {
                showError(`Error al procesar los archivos: ${err.message || err}`);
            }
            console.error(err);
        } finally {
            clearInterval(timerInterval);
            clearTimeout(abortTimeout);
            loader.textContent = "Cargando datos...";
            loader.classList.add("hidden");
        }
    }
    
    function populateFilters(data) {
        document.getElementById("filters-container").style.display = "flex";
        
        const niveles = new Set();
        const grados = new Set();
        const secciones = new Set();
        
        data.results.forEach(s => {
            if (s.nivel && s.nivel !== "DESCONOCIDO") niveles.add(s.nivel);
            if (s.grado && s.grado !== "DESCONOCIDO") grados.add(s.grado);
            if (s.seccion && s.seccion !== "DESCONOCIDO") secciones.add(s.seccion);
        });
        
        data.not_found.forEach(s => {
            if (s.nivel && s.nivel !== "DESCONOCIDO") niveles.add(s.nivel);
            if (s.grado && s.grado !== "DESCONOCIDO") grados.add(s.grado);
            if (s.seccion && s.seccion !== "DESCONOCIDO") secciones.add(s.seccion);
        });

        fillSelect(nivelFilter, Array.from(niveles));
        fillSelect(gradoFilter, Array.from(grados));
        fillSelect(seccionFilter, Array.from(secciones));
    }
    
    function fillSelect(selectEl, items) {
        selectEl.innerHTML = '<option value="TODOS">TODOS</option>';
        items.sort().forEach(item => {
            const opt = document.createElement("option");
            opt.value = item;
            opt.textContent = item;
            selectEl.appendChild(opt);
        });
    }

    function applyFilters() {
        if (!globalData) return;
        
        const nFilter = nivelFilter.value;
        const gFilter = gradoFilter.value;
        const sFilter = seccionFilter.value;
        
        // Update header text based on filters
        const displayNivel = nFilter === "TODOS" ? globalData.nivel : nFilter;
        const displayGrado = gFilter === "TODOS" ? globalData.grado : gFilter;
        const displaySeccion = sFilter === "TODOS" ? globalData.seccion : sFilter;
        
        const nivelText = displayNivel && displayNivel !== "DESCONOCIDO" ? `Nivel: ${displayNivel} | ` : "";
        const monthText = globalData.month_name ? ` | Mes: ${globalData.month_name} ${globalData.year}` : "";
        detectedGradeSpan.textContent = `${nivelText}Grado: ${displayGrado} | Sección: ${displaySeccion}${monthText}`;
        
        const filteredResults = globalData.results.filter(s => {
            return (nFilter === "TODOS" || s.nivel === nFilter) &&
                   (gFilter === "TODOS" || s.grado === gFilter) &&
                   (sFilter === "TODOS" || s.seccion === sFilter);
        });
        
        const filteredNotFound = globalData.not_found.filter(s => {
            return (nFilter === "TODOS" || s.nivel === nFilter) &&
                   (gFilter === "TODOS" || s.grado === gFilter) &&
                   (sFilter === "TODOS" || s.seccion === sFilter);
        });
        
        // extra_students no tienen n/g/s asique los mostramos solo si TODO es TODOS, o siempre
        let filteredExtra = [];
        if (nFilter === "TODOS" && gFilter === "TODOS" && sFilter === "TODOS") {
            filteredExtra = globalData.extra_students;
        }

        const viewData = {
            days: globalData.days,
            results: filteredResults,
            not_found: filteredNotFound,
            extra_students: filteredExtra
        };

        let dataEl = document.getElementById("hidden-view-data");
        if (!dataEl) {
            dataEl = document.createElement("div");
            dataEl.id = "hidden-view-data";
            dataEl.style.display = "none";
            document.body.appendChild(dataEl);
        }
        dataEl.textContent = JSON.stringify(viewData);

        renderTable(viewData);
        renderNotFound(viewData.not_found, viewData.extra_students);
        renderSummary(viewData);
    }
    
    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.classList.remove("hidden");
    }
    
    function renderTable(data) {
        // Render headers
        tableHeader.innerHTML = `<th>Apellidos y Nombres</th>`;
        tableFooterRow.innerHTML = `<th>Apellidos y Nombres</th>`;
        
        data.days.forEach(dayInfo => {
            const th = document.createElement("th");
            th.className = "day-header";
            if (dayInfo.day === 'S' || dayInfo.day === 'D') {
                th.classList.add("weekend");
            }
            th.innerHTML = `
                <span class="day-num">${dayInfo.num}</span>
                <span class="day-name">${dayInfo.day}</span>
            `;
            tableHeader.appendChild(th);
            
            const thFooter = th.cloneNode(true);
            tableFooterRow.appendChild(thFooter);
        });
        
        // Render body
        tableBody.innerHTML = "";
        data.results.forEach(row => {
            const tr = document.createElement("tr");
            
            // Name cell
            const tdName = document.createElement("td");
            tdName.className = "student-name";
            tdName.textContent = row.name;
            tr.appendChild(tdName);
            
            // Attendance cells
            row.attendance.forEach((val, i) => {
                const tdAtt = document.createElement("td");
                tdAtt.className = "att-cell";
                
                // Añadir clase para fin de semana
                if (data.days[i].day === 'S' || data.days[i].day === 'D') {
                    tdAtt.classList.add("weekend");
                }
                
                // Style based on value
                let valClass = "";
                if (val === ".") valClass = "val-P";
                else if (val === "F") valClass = "val-F";
                else if (val === "T") valClass = "val-T";
                else if (val === "J") valClass = "val-J";
                else if (val === "U") valClass = "val-U";
                
                if (valClass) {
                    tdAtt.innerHTML = `<span class="${valClass}">${val}</span>`;
                } else {
                    tdAtt.textContent = val;
                }
                
                tr.appendChild(tdAtt);
            });
            
            tableBody.appendChild(tr);
        });
        
        attendanceTable.classList.remove("hidden");
    }
    
    function renderNotFound(notFoundList, extraList) {
        if ((!notFoundList || notFoundList.length === 0) && (!extraList || extraList.length === 0)) {
            notFoundContainer.classList.add("hidden");
            return;
        }

        notFoundContainer.classList.remove("hidden");
        notFoundBody.innerHTML = "";

        if (notFoundList && notFoundList.length > 0) {
            notFoundList.forEach(student => {
                const tr = document.createElement("tr");
                const tdName = document.createElement("td");
                tdName.textContent = student.name;
                const tdNgs = document.createElement("td");
                tdNgs.textContent = student.ngs || "SIN REGISTRO";
                tdNgs.style.color = "#ef4444";
                
                tr.appendChild(tdName);
                tr.appendChild(tdNgs);
                notFoundBody.appendChild(tr);
            });
        }
        
        if (extraList && extraList.length > 0) {
            extraList.forEach(student => {
                const tr = document.createElement("tr");
                const tdName = document.createElement("td");
                tdName.textContent = student.name;
                const tdNgs = document.createElement("td");
                tdNgs.textContent = student.ngs || "NO ESTÁ EN SIAGIE";
                tdNgs.style.color = "#f59e0b"; // Naranja
                
                tr.appendChild(tdName);
                tr.appendChild(tdNgs);
                notFoundBody.appendChild(tr);
            });
        }
    }
    
    function renderSummary(data) {
        const foundCount = data.results ? data.results.length : 0;
        const notFoundCount = data.not_found ? data.not_found.length : 0;
        const total = foundCount + notFoundCount;
        
        totalStudentsSpan.textContent = total;
        let timingStr = "";
        if (globalData && globalData.debug) {
            const d = globalData.debug;
            timingStr = ` | ⏱ ${d.total_s}s (SIAGIE ${d.phase1_siagie_s}s · asistencia ${d.phase2_attendance_s}s)`;
        }
        studentDetailsSpan.textContent = `(${foundCount} encontrados, ${notFoundCount} no encontrados)${timingStr}`;
        summaryContainer.classList.remove("hidden");
    }
});
