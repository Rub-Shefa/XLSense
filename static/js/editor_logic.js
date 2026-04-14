// ==========================================
// 1. GLOBAL VARIABLES & STATE
// ==========================================
let historyStack = [];
let redoStack = [];
let ignoreNextSave = false;
let activeCell = null;
let cellFormulas = new Map();
let originalState = { fontFamily: '', fontSize: '', backgroundColor: '', color: '' };

// ==========================================
// 2. UNDO / REDO SYSTEM
// ==========================================
function captureState() {
    if (ignoreNextSave) { ignoreNextSave = false; return; }
    
    const headers = Array.from(document.querySelectorAll('#headerRow th:not(.row-header-cell)')).map(th => {
        const select = th.querySelector('.mapping-select');
        return {
            outerHTML: th.outerHTML,
            text: th.querySelector('.header-label') ? th.querySelector('.header-label').innerText.trim() : '',
            selectedValue: select ? select.value : ''
        };
    });

    const rows = [];
    document.querySelectorAll('#tableBody tr').forEach(tr => {
        const rowData = [];
        tr.querySelectorAll('td.editable-cell').forEach(td => {
            rowData.push({
                text: td.innerText,
                style: td.style.cssText, // Saves all formatting!
                formula: cellFormulas.get(td) || '' // Saves math formulas!
            });
        });
        rows.push(rowData);
    });

    historyStack.push({ headers: headers, rows: rows });
    redoStack = [];
    if (historyStack.length > 50) historyStack.shift();
}

function restoreState(state) {
    if (!state) return;
    ignoreNextSave = true;
    
    const headerRow = document.getElementById('headerRow');
    const rowHeaderCell = headerRow.querySelector('.row-header-cell'); 
    
    // Safely get the header HTML in case it gets lost
    let newHeaderHtml = rowHeaderCell ? rowHeaderCell.outerHTML : ''; 
    state.headers.forEach(h => { newHeaderHtml += h.outerHTML; });
    headerRow.innerHTML = newHeaderHtml; 

    const selects = headerRow.querySelectorAll('.mapping-select');
    const labels = headerRow.querySelectorAll('.header-label');
    state.headers.forEach((h, idx) => {
        if (selects[idx]) selects[idx].value = h.selectedValue;
        if (labels[idx]) labels[idx].innerText = h.text;
    });

    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    cellFormulas.clear();

    state.rows.forEach((row, ri) => {
        const tr = document.createElement('tr');
        let html = `<td class="row-header-cell"><span style="font-size:0.7rem;">${ri+1}</span><button class="row-delete-btn" onclick="deleteRowHandler(this)"><i class="fas fa-trash-alt"></i></button></td>`;
        
        row.forEach(cellData => { 
            html += `<td contenteditable="true" class="editable-cell" style="${cellData.style || ''}">${escapeHtml(cellData.text)}</td>`; 
        });
        tr.innerHTML = html;
        tbody.appendChild(tr);

        const newCells = tr.querySelectorAll('td.editable-cell');
        row.forEach((cellData, ci) => {
            if (cellData.formula) {
                cellFormulas.set(newCells[ci], cellData.formula);
            }
        });
    });

    attachCellEvents();
    updateStatusBar();
    renumberRows();
    activeCell = null;
}

function undo() {
    if (historyStack.length < 2) return;
    const current = historyStack.pop();
    redoStack.push(current);
    const prev = historyStack[historyStack.length-1];
    if (prev) restoreState(prev);
}

function redo() {
    if (redoStack.length === 0) return;
    const next = redoStack.pop();
    historyStack.push(next);
    restoreState(next);
}

function escapeHtml(str) { 
    if (typeof str !== 'string') return '';
    return str.replace(/[&<>]/g, function(m){ 
        if(m==='&') return '&amp;'; 
        if(m==='<') return '&lt;'; 
        if(m==='>') return '&gt;'; 
        return m;
    }); 
}

// ==========================================
// 3. ENHANCED FORMULA EVALUATION
// ==========================================
function evaluateFormula(formula, getCellValue) {
    if (!formula.startsWith('=')) return null;
    const expr = formula.substring(1).trim();

    const funcMatch = expr.match(/^(SUM|AVERAGE|COUNT|MAX|MIN)\((.*)\)$/i);
    if (funcMatch) {
        const func = funcMatch[1].toUpperCase();
        const argsString = funcMatch[2];
        const args = parseArguments(argsString);
        let allValues = [];
        for (let arg of args) {
            if (arg.includes(':')) {
                const [start, end] = arg.split(':');
                const values = getRangeValues(start, end, getCellValue);
                allValues.push(...values);
            } else {
                let val = getCellValue(arg);
                if (!isNaN(val) && val !== "") allValues.push(Number(val));
            }
        }
        if (func === 'SUM') return allValues.reduce((a,b)=>a+b, 0);
        if (func === 'AVERAGE') return allValues.length ? allValues.reduce((a,b)=>a+b,0)/allValues.length : 0;
        if (func === 'COUNT') return allValues.length;
        if (func === 'MAX') return allValues.length ? Math.max(...allValues) : 0;
        if (func === 'MIN') return allValues.length ? Math.min(...allValues) : 0;
    }
    try {
        let evalExpr = expr.replace(/[A-Z]+[0-9]+/gi, (ref) => {
            let val = getCellValue(ref);
            return isNaN(val) ? 0 : val;
        });
        return Function('"use strict";return (' + evalExpr + ')')();
    } catch(e) { return null; }
}

function parseArguments(argsString) {
    let args = []; let current = ''; let depth = 0;
    for (let ch of argsString) {
        if (ch === '(') depth++;
        if (ch === ')') depth--;
        if (ch === ',' && depth === 0) { args.push(current.trim()); current = ''; } 
        else { current += ch; }
    }
    if (current.trim()) args.push(current.trim());
    return args;
}

function getRangeValues(start, end, getCellValue) {
    const startCol = start.match(/[A-Z]+/)[0]; const startRow = parseInt(start.match(/[0-9]+/)[0]);
    const endCol = end.match(/[A-Z]+/)[0]; const endRow = parseInt(end.match(/[0-9]+/)[0]);
    const values = [];
    const startColNum = colToNum(startCol); const endColNum = colToNum(endCol);
    for (let r = startRow; r <= endRow; r++) {
        for (let c = startColNum; c <= endColNum; c++) {
            let val = getCellValue(numToCol(c) + r);
            if (!isNaN(val) && val !== "") values.push(Number(val));
        }
    }
    return values;
}
function colToNum(col) { let num=0; for(let i=0;i<col.length;i++) num = num*26 + (col.charCodeAt(i)-64); return num-1; }
function numToCol(num) { let col=""; while(num>=0){ col=String.fromCharCode(65+(num%26))+col; num=Math.floor(num/26)-1; } return col; }

// ==========================================
// 4. CELL HANDLING & UI UPDATES
// ==========================================
function updateStatusBar() {
    document.getElementById('rowCount').innerText = document.querySelectorAll('#tableBody tr').length;
    document.getElementById('colCount').innerText = document.querySelectorAll('#headerRow th:not(.row-header-cell)').length;
}

function getCellValueFromDOM(ref) {
    const match = ref.match(/([A-Z]+)([0-9]+)/);
    if (!match) return null;
    const colIndex = colToNum(match[1]); const rowIndex = parseInt(match[2]) - 1;
    const tbody = document.getElementById('tableBody');
    if (rowIndex >= 0 && rowIndex < tbody.rows.length) {
        const cell = tbody.rows[rowIndex].cells[colIndex+1]; 
        if (cell) return cell.innerText.trim();
    }
    return null;
}

function setActiveCell(cell) {
    if (activeCell) activeCell.classList.remove('cell-active');
    activeCell = cell;
    if (activeCell) {
        activeCell.classList.add('cell-active');
        const rowIdx = activeCell.parentElement.rowIndex;
        const colIdx = activeCell.cellIndex - 1;
        document.getElementById('activeCellRef').innerText = `${numToCol(colIdx)}${rowIdx}`;
        document.getElementById('formulaInput').value = cellFormulas.get(activeCell) || activeCell.innerText;

        const style = window.getComputedStyle(activeCell);
        originalState = {
            fontFamily: activeCell.style.fontFamily || style.fontFamily,
            fontSize: activeCell.style.fontSize || style.fontSize,
            backgroundColor: activeCell.style.backgroundColor || style.backgroundColor,
            color: activeCell.style.color || style.color
        };
        
        const fontDropdown = document.querySelector('#fontDropdown .dropdown-selected');
        const sizeDropdown = document.querySelector('#sizeDropdown .dropdown-selected');
        if(fontDropdown) fontDropdown.innerText = originalState.fontFamily.split(',')[0].replace(/['"]/g, '');
        if(sizeDropdown) sizeDropdown.innerText = originalState.fontSize.replace('px', '');
    } else {
        document.getElementById('activeCellRef').innerText = '';
        document.getElementById('formulaInput').value = '';
    }
}

function attachCellEvents() {
    // FIX: Using onfocus and oninput instead of addEventListener prevents duplicate firing 
    // when the table is rebuilt by the restoreState (Undo/Redo) function.
    document.querySelectorAll('.editable-cell').forEach(cell => {
        cell.onfocus = () => setActiveCell(cell);
        cell.oninput = () => captureState();
    });
}

function updateCellFromFormulaBar() {
    if (!activeCell) return;
    const newValue = document.getElementById('formulaInput').value;
    if (newValue.startsWith('=')) {
        cellFormulas.set(activeCell, newValue);
        const result = evaluateFormula(newValue, getCellValueFromDOM);
        activeCell.innerText = (result !== null && !isNaN(result)) ? result : newValue;
    } else {
        cellFormulas.delete(activeCell);
        activeCell.innerText = newValue;
    }
    captureState();
}

document.getElementById('formulaInput').addEventListener('change', updateCellFromFormulaBar);
document.getElementById('formulaInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        updateCellFromFormulaBar();
        if (activeCell && activeCell.parentElement.nextElementSibling) {
            const nextCell = activeCell.parentElement.nextElementSibling.children[activeCell.cellIndex];
            if (nextCell) nextCell.focus();
        }
    }
});

document.querySelectorAll('.func-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (!activeCell) return;
        const func = btn.getAttribute('data-func');
        const rowIdx = activeCell.parentElement.rowIndex;
        const colIdx = numToCol(activeCell.cellIndex - 1);
        const formula = `=${func.toUpperCase()}(${colIdx}1:${colIdx}${rowIdx > 1 ? rowIdx-1 : 1})`;
        document.getElementById('formulaInput').value = formula;
        updateCellFromFormulaBar();
    });
});

// ==========================================
// 5. FORMATTING TOOLBAR & COLORS
// ==========================================
function setupFormattingToolbar() {
    document.querySelectorAll('.custom-dropdown').forEach(dropdown => {
        dropdown.querySelector('.dropdown-selected').addEventListener('click', function(e) {
            e.stopPropagation();
            document.querySelectorAll('.custom-dropdown').forEach(d => { if(d !== dropdown) d.classList.remove('active') });
            dropdown.classList.toggle('active');
        });
    });
    document.addEventListener('click', () => {
        document.querySelectorAll('.custom-dropdown').forEach(d => d.classList.remove('active'));
    });

    function setupDropdownItems(dropdownId, styleProperty) {
        document.querySelectorAll(`#${dropdownId} [data-val]`).forEach(item => {
            item.addEventListener('mouseover', function() { if (activeCell) activeCell.style[styleProperty] = this.getAttribute('data-val'); });
            item.addEventListener('mouseout', function() { if (activeCell) activeCell.style[styleProperty] = originalState[styleProperty]; });
            item.addEventListener('click', function() {
                if (activeCell) {
                    const val = this.getAttribute('data-val');
                    activeCell.style[styleProperty] = val;
                    originalState[styleProperty] = val;
                    document.querySelector(`#${dropdownId} .dropdown-selected`).innerText = this.innerText;
                    captureState();
                }
            });
        });
    }
    setupDropdownItems('fontDropdown', 'fontFamily');
    setupDropdownItems('sizeDropdown', 'fontSize');

    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            if (!activeCell) return;
            const cmd = this.getAttribute('data-cmd');
            if (cmd === 'bold') activeCell.style.fontWeight = (activeCell.style.fontWeight === 'bold' || activeCell.style.fontWeight === '700') ? 'normal' : 'bold';
            else if (cmd === 'italic') activeCell.style.fontStyle = activeCell.style.fontStyle === 'italic' ? 'normal' : 'italic';
            else if (cmd === 'underline') activeCell.style.textDecoration = activeCell.style.textDecoration.includes('underline') ? 'none' : 'underline';
            captureState();
        });
    });

    const excelColors = [
        '#ffffff', '#000000', '#eeece1', '#1f497d', '#4f81bd', '#c0504d',
        '#f2f2f2', '#808080', '#ddd9c3', '#c6d9f1', '#dbe5f1', '#f2dcdb',
        '#d9d9d9', '#595959', '#c4bd97', '#8db4e2', '#b8cce4', '#e6b8b7',
        '#bfbfbf', '#404040', '#938953', '#548dd4', '#95b3d7', '#d99694',
        '#ff0000', '#00ff00', '#0000ff', '#ffff00', '#00ffff', '#ff00ff'
    ];

    window.previewColor = function(color, isText) { if (activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = color; };
    window.revertColor = function(isText) { if (activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = originalState[isText ? 'color' : 'backgroundColor']; };
    window.applyColor = function(color, isText) {
        if (!activeCell) return;
        activeCell.style[isText ? 'color' : 'backgroundColor'] = color;
        originalState[isText ? 'color' : 'backgroundColor'] = color;
        document.querySelector(`#${isText ? 'textColorDropdown' : 'fillColorDropdown'} .color-indicator`).style.backgroundColor = color;
        captureState();
    };

    function buildPalette(gridId, isText) {
        const grid = document.getElementById(gridId);
        if (!grid) return;
        excelColors.forEach(color => {
            const swatch = document.createElement('div');
            swatch.className = 'color-swatch'; swatch.style.backgroundColor = color;
            swatch.addEventListener('click', () => applyColor(color, isText));
            swatch.addEventListener('mouseover', () => previewColor(color, isText));
            swatch.addEventListener('mouseout', () => revertColor(isText));
            grid.appendChild(swatch);
        });
    }
    buildPalette('fillPaletteGrid', false);
    buildPalette('textPaletteGrid', true);

    const nativeFill = document.getElementById('nativeFillPicker');
    const nativeText = document.getElementById('nativeTextPicker');
    if(nativeFill) nativeFill.addEventListener('input', (e) => applyColor(e.target.value, false));
    if(nativeText) nativeText.addEventListener('input', (e) => applyColor(e.target.value, true));
}

// ==========================================
// 6. ROW/COLUMN OPERATIONS
// ==========================================
function addRow() {
    const tbody = document.getElementById('tableBody');
    const colCount = document.querySelectorAll('#headerRow th:not(.row-header-cell)').length;
    const newRow = document.createElement('tr');
    let html = `<td class="row-header-cell"><span style="font-size:0.7rem;">${tbody.children.length+1}</span><button class="row-delete-btn" onclick="deleteRowHandler(this)"><i class="fas fa-trash-alt"></i></button></td>`;
    for(let i=0; i<colCount; i++) html += `<td contenteditable="true" class="editable-cell"></td>`;
    newRow.innerHTML = html;
    tbody.appendChild(newRow);
    attachCellEvents(); updateStatusBar(); renumberRows(); captureState();
}
function deleteRowHandler(btn) {
    if(document.querySelectorAll('#tableBody tr').length <= 1) return alert("At least one row required");
    const row = btn.closest('tr');
    row.querySelectorAll('.editable-cell').forEach(cell => cellFormulas.delete(cell));
    row.remove();
    attachCellEvents(); updateStatusBar(); renumberRows(); captureState();
}
function addColumn() {
    const headerRow = document.getElementById('headerRow');
    const newTh = document.createElement('th');
    newTh.className = 'header-custom'; newTh.setAttribute('data-colname', 'New_Column');
    let dbOptionsHtml = '';
    const sampleSelect = document.querySelector('.mapping-select');
    if (sampleSelect) {
        sampleSelect.querySelectorAll('option').forEach(opt => { dbOptionsHtml += `<option value="${opt.value.replace(/"/g, '&quot;')}">${opt.textContent}</option>`; });
    }
    newTh.innerHTML = `<div class="header-content"><button class="del-col" onclick="deleteColumnHandler(this)"><i class="fas fa-times"></i></button><span class="header-label" contenteditable="true">New_Column</span><select class="mapping-select" onchange="handleMappingChange(this)"><option value="">-- Map to DB field --</option>${dbOptionsHtml}</select></div>`;
    headerRow.appendChild(newTh);
    document.querySelectorAll('#tableBody tr').forEach(row => {
        const td = document.createElement('td'); td.contentEditable = 'true'; td.className = 'editable-cell';
        row.appendChild(td);
    });
    attachCellEvents(); updateStatusBar(); captureState();
}
function deleteColumnHandler(btn) {
    const th = btn.closest('th'); const idx = th.cellIndex; 
    th.remove();
    document.querySelectorAll('#tableBody tr').forEach(row => {
        const cell = row.cells[idx]; if (cell) cellFormulas.delete(cell);
        row.deleteCell(idx); 
    });
    attachCellEvents(); updateStatusBar(); captureState();
}
function renumberRows() {
    document.querySelectorAll('#tableBody tr').forEach((row, i) => {
        const span = row.querySelector('.row-header-cell span');
        if (span) span.innerText = i+1;
    });
}
window.deleteRowHandler = deleteRowHandler;
window.deleteColumnHandler = deleteColumnHandler;
window.handleMappingChange = function(select) {
    const th = select.closest('th');
    th.className = select.value ? 'header-matched' : 'header-custom';
    captureState();
};

// ==========================================
// 7. KEYBOARD NAVIGATION
// ==========================================
function attachKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
        if ((e.ctrlKey || e.metaKey) && e.key === 'y') { e.preventDefault(); redo(); return; }
        if (!activeCell) return;
        const row = activeCell.parentElement; const tbody = document.getElementById('tableBody');
        const rows = Array.from(tbody.querySelectorAll('tr')); const rowIndex = rows.indexOf(row);
        const cells = Array.from(row.querySelectorAll('td.editable-cell')); const colIndex = cells.indexOf(activeCell);
        
        if (e.key === 'Tab') {
            e.preventDefault();
            let nextCell = null;
            if (e.shiftKey) {
                if (colIndex > 0) nextCell = cells[colIndex-1];
                else if (rowIndex > 0) nextCell = Array.from(rows[rowIndex-1].querySelectorAll('td.editable-cell')).pop();
            } else {
                if (colIndex < cells.length-1) nextCell = cells[colIndex+1];
                else if (rowIndex < rows.length-1) nextCell = rows[rowIndex+1].querySelector('td.editable-cell');
            }
            if (nextCell) nextCell.focus();
        } else if (e.key === 'Enter') {
            e.preventDefault(); updateCellFromFormulaBar();
            if (rowIndex < rows.length-1) rows[rowIndex+1].querySelectorAll('td.editable-cell')[colIndex]?.focus();
        } else if (e.key === 'ArrowUp' && rowIndex > 0) { e.preventDefault(); rows[rowIndex-1].querySelectorAll('td.editable-cell')[colIndex]?.focus(); } 
        else if (e.key === 'ArrowDown' && rowIndex < rows.length-1) { e.preventDefault(); rows[rowIndex+1].querySelectorAll('td.editable-cell')[colIndex]?.focus(); } 
        else if (e.key === 'ArrowLeft' && colIndex > 0) { e.preventDefault(); cells[colIndex-1].focus(); } 
        else if (e.key === 'ArrowRight' && colIndex < cells.length-1) { e.preventDefault(); cells[colIndex+1].focus(); }
    });
}

// ==========================================
// 8. SAVE WORKBOOK
// ==========================================
async function saveData() {
    const saveBtn = document.getElementById('saveProcessBtn');
    const originalHtml = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> Saving...';
    saveBtn.disabled = true;

    try {
        const headers = []; const colIndicesToKeep = []; const mappings = {};
        document.querySelectorAll('#headerRow th:not(.row-header-cell)').forEach((th, idx) => {
            const isTemplateOnly = th.classList.contains('header-template-only');
            const select = th.querySelector('.mapping-select');
            const isMapped = select && select.value !== "";
            const headerText = th.querySelector('.header-label').innerText.trim();

            if (!isTemplateOnly || isMapped) {
                colIndicesToKeep.push(idx);
                headers.push(isMapped ? select.value : headerText);
                if (isMapped) mappings[headerText] = select.value;
            }
        });

        const rows = [];
        document.querySelectorAll('#tableBody tr').forEach(tr => {
            const rowData = []; const cells = tr.querySelectorAll('td.editable-cell');
            colIndicesToKeep.forEach(idx => {
                if (cells[idx]) {
                    const cell = cells[idx];
                    rowData.push({
                        value: cell.innerText.trim(),
                        bold: cell.style.fontWeight === "bold" || cell.style.fontWeight === "700",
                        italic: cell.style.fontStyle === "italic",
                        underline: cell.style.textDecoration.includes("underline"),
                        color: cell.style.color || null,
                        bg: cell.style.backgroundColor || null,
                        fontFamily: cell.style.fontFamily || null,
                        fontSize: cell.style.fontSize || null
                    });
                }
            });
            rows.push(rowData);
        });

        const response = await fetch(window.DJANGO_VARS.saveUrl, {
            method: "POST", 
            headers: { 
                "Content-Type": "application/json", 
                "X-CSRFToken": window.DJANGO_VARS.csrfToken 
            },
            body: JSON.stringify({ headers, rows, mappings })
        });

        let result;
        try { result = await response.json(); } 
        catch(parseErr) { showTemporaryToast("Server crashed! Check your VSCode terminal.", "error"); saveBtn.innerHTML = originalHtml; saveBtn.disabled = false; return; }

        if (response.ok && result.status === "success") {
            showTemporaryToast("Saved successfully! Redirecting...", "success");
            setTimeout(() => { 
                window.location.href = window.DJANGO_VARS.uploadUrl + "?processed_id=" + result.new_file_id + "&preview=true"; 
            }, 800);
        } else { showTemporaryToast("Error: " + (result.error || "Failed to save"), "error"); }
    } catch(e) { showTemporaryToast("Connection lost.", "error"); } 
    finally { saveBtn.innerHTML = originalHtml; saveBtn.disabled = false; }
}

function showTemporaryToast(msg, type) {
    let toast = document.createElement('div'); toast.innerText = msg;
    toast.style.position = 'fixed'; toast.style.bottom = '70px'; toast.style.right = '30px';
    toast.style.background = type === 'success' ? '#1e6f3f' : '#d13438'; toast.style.color = 'white';
    toast.style.padding = '12px 24px'; toast.style.borderRadius = '40px'; toast.style.fontWeight = '500'; toast.style.zIndex = '9999';
    document.body.appendChild(toast); setTimeout(() => toast.remove(), 2500);
}

// ==========================================
// 9. INITIALIZATION
// ==========================================
function init() {
    attachCellEvents();
    updateStatusBar();
    renumberRows();
    attachKeyboardNavigation();
    setupFormattingToolbar(); 
    
    document.getElementById('addRowBtn').onclick = addRow;
    document.getElementById('addColBtn').onclick = addColumn;
    document.getElementById('undoBtn').onclick = undo;
    document.getElementById('redoBtn').onclick = redo;
    document.getElementById('saveProcessBtn').onclick = saveData;
    
    const firstCell = document.querySelector('#tableBody td.editable-cell');
    if (firstCell) { firstCell.focus(); setActiveCell(firstCell); }
    captureState();
    
    const savedMappings = window.DJANGO_VARS.savedMappings;
    if (savedMappings && Object.keys(savedMappings).length > 0) {
        document.querySelectorAll('#headerRow th:not(.row-header-cell)').forEach(th => {
            const labelSpan = th.querySelector('.header-label');
            if (!labelSpan) return;
            const colName = labelSpan.innerText.trim();
            if (savedMappings[colName]) {
                const select = th.querySelector('.mapping-select');
                if (select) { select.value = savedMappings[colName]; handleMappingChange(select); }
            }
        });
    }

    // Restore Saved Styles from Database
    const styleData = window.DJANGO_VARS.styleData;
    if (styleData && Array.isArray(styleData) && styleData.length > 0) {
        const trs = document.querySelectorAll('#tableBody tr');
        
        styleData.forEach((row, ri) => {
            if (trs[ri]) {
                const tds = trs[ri].querySelectorAll('td.editable-cell');
                row.forEach((cellData, ci) => {
                    if (tds[ci] && typeof cellData === 'object') {
                        // Apply all saved formatting back to the cells
                        if (cellData.bold) tds[ci].style.fontWeight = 'bold';
                        if (cellData.italic) tds[ci].style.fontStyle = 'italic';
                        if (cellData.underline) tds[ci].style.textDecoration = 'underline';
                        if (cellData.color) tds[ci].style.color = cellData.color;
                        if (cellData.bg) tds[ci].style.backgroundColor = cellData.bg;
                        if (cellData.fontFamily) tds[ci].style.fontFamily = cellData.fontFamily;
                        if (cellData.fontSize) tds[ci].style.fontSize = cellData.fontSize;
                    }
                });
            }
        });
        
        // Take a snapshot so "Undo" remembers these loaded styles
        captureState(); 
    }
}

init();