// ==========================================
// 1. GLOBAL VARIABLES & STATE
// ==========================================
let historyStack = [];
let redoStack = [];
let activeCell = null;
let cellFormulas = new Map();
let lastStateJson = null; 
let originalState = { fontFamily: '', fontSize: '', backgroundColor: '', color: '' };
let isRestoring = false; 
let valueDisplay = document.getElementById('valueDisplay');
// ==========================================
// 2. UNDO / REDO SYSTEM
// ==========================================

function captureState() {
    if (isRestoring) return;
    try {
        const headers = Array.from(document.querySelectorAll('#headerRow th:not(.row-header-cell)')).map(th => {
            const select = th.querySelector('.mapping-select');
            const label = th.querySelector('.header-label');
            return {
                outerHTML: th.outerHTML,
                text: label ? label.innerText.trim() : '',
                selectedValue: select ? select.value : ''
            };
        });

        const rows = [];
        document.querySelectorAll('#tableBody tr').forEach(tr => {
            const rowData = [];
            tr.querySelectorAll('td.editable-cell').forEach(td => {
                // SAFETY: Check if 'td' exists before accessing .innerText or .style
                rowData.push({
                    text: td ? td.innerText : '',
                    style: td ? td.style.cssText : '',
                    formula: (td && cellFormulas.has(td)) ? cellFormulas.get(td) : ''
                });
            });
            rows.push(rowData);
        });

        const currentState = { headers: headers, rows: rows };
        const currentStateJson = JSON.stringify(currentState);

        if (currentStateJson !== lastStateJson) {
            historyStack.push(currentState);
            lastStateJson = currentStateJson;
            redoStack = []; 
            if (historyStack.length > 50) historyStack.shift(); 
        }
    } catch (e) {
        console.warn("Capture state error (Caught):", e);
    }
}

function restoreState(state) {
    if (!state) return;
    
    isRestoring = true;

    try {
        const headerRow = document.getElementById('headerRow');
        if (!headerRow) return;
        
        // 1. Restore Headers Structure
        const rowHeaderCell = headerRow.querySelector('.row-header-cell'); 
        let newHeaderHtml = rowHeaderCell ? rowHeaderCell.outerHTML : ''; 
        state.headers.forEach(h => { newHeaderHtml += h.outerHTML; });
        headerRow.innerHTML = newHeaderHtml; 

        // 2. Sync Select values
        const selects = headerRow.querySelectorAll('.mapping-select');
        const labels = headerRow.querySelectorAll('.header-label');
        state.headers.forEach((h, idx) => {
            if (selects[idx]) selects[idx].value = h.selectedValue;
            if (labels[idx]) labels[idx].innerText = h.text;
            const th = selects[idx]?.closest('th');
            if (th) th.className = h.selectedValue ? 'header-matched' : 'header-custom';
        });

        // 3. Clear and Rebuild Body
        const tbody = document.getElementById('tableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        cellFormulas.clear();

        state.rows.forEach((row, ri) => {
            const tr = document.createElement('tr');
            let html = `<td class="row-header-cell"><span style="font-size:0.7rem;">${ri+1}</span><button class="row-delete-btn" onclick="deleteRowHandler(this)"><i class="fas fa-trash-alt"></i></button></td>`;
            
            row.forEach(cellData => { 
                // THE FIX: Escape double quotes in the style string so it doesn't break the HTML attribute!
                const safeStyle = (cellData.style || '').replace(/"/g, '&quot;');
                html += `<td contenteditable="true" class="editable-cell" style="${safeStyle}">${escapeHtml(cellData.text)}</td>`; 
            });
            tr.innerHTML = html;
            tbody.appendChild(tr);

            const newCells = tr.querySelectorAll('td.editable-cell');
            row.forEach((cellData, ci) => {
                if (cellData.formula && newCells[ci]) {
                    cellFormulas.set(newCells[ci], cellData.formula);
                }
            });
        });

        // 4. Cleanup
        attachCellEvents();
        updateStatusBar();
        renumberRows();
        lastStateJson = JSON.stringify(state);
        activeCell = null; 
    } catch (e) {
        console.error("Critical error during Undo restoration:", e);
    }
    finally {
        setTimeout(() => { isRestoring = false; }, 10); 
    }
}

function undo() {
    if (historyStack.length < 2) return; // Need at least the current state and one previous
    const current = historyStack.pop();
    redoStack.push(current);
    const prev = historyStack[historyStack.length - 1];
    restoreState(prev);
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
                if (!isNaN(val) && val !== "" && val !== null) allValues.push(Number(val));
            }
        }
        if (func === 'SUM') return allValues.reduce((a, b) => a + b, 0);
        if (func === 'AVERAGE') return allValues.length ? allValues.reduce((a, b) => a + b, 0) / allValues.length : 0;
        if (func === 'COUNT') return allValues.length;
        if (func === 'MAX') return allValues.length ? Math.max(...allValues) : 0;
        if (func === 'MIN') return allValues.length ? Math.min(...allValues) : 0;
    }
    try {
        let evalExpr = expr.replace(/[A-Z]+[0-9]+/gi, (ref) => {
            let val = getCellValue(ref);
            return isNaN(val) || val === "" ? 0 : val;
        });
        return Function('"use strict";return (' + evalExpr + ')')();
    } catch (e) { return "#VALUE!"; }
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
            if (!isNaN(val) && val !== "" && val !== null) values.push(Number(val));
        }
    }
    return values;
}
function colToNum(col) { let num = 0; for (let i = 0; i < col.length; i++) num = num * 26 + (col.charCodeAt(i) - 64); return num - 1; }
function numToCol(num) { let col = ""; while (num >= 0) { col = String.fromCharCode(65 + (num % 26)) + col; num = Math.floor(num / 26) - 1; } return col; }

/// ==========================================
// 4. CELL HANDLING & UI UPDATES
// ==========================================
function updateStatusBar() {
    const rEl = document.getElementById('rowCount');
    const cEl = document.getElementById('colCount');
    if (rEl) rEl.innerText = document.querySelectorAll('#tableBody tr').length;
    if (cEl) cEl.innerText = document.querySelectorAll('#headerRow th:not(.row-header-cell)').length;
}

function getCellValueFromDOM(ref) {
    const match = ref.match(/([A-Z]+)([0-9]+)/);
    if (!match) return null;
    const colIndex = colToNum(match[1]); const rowIndex = parseInt(match[2]) - 1;
    const tbody = document.getElementById('tableBody');
    if (tbody && rowIndex >= 0 && rowIndex < tbody.rows.length) {
        const cell = tbody.rows[rowIndex].cells[colIndex + 1]; 
        if (cell) return cell.innerText.trim();
    }
    return null;
}


window.updateDropdownUI = function(dropdownId, displayValue) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;
    const selectedEl = dropdown.querySelector('.selected-text') || dropdown.querySelector('.dropdown-selected');
    if (selectedEl) {
        // Find the text node to update so we don't accidentally delete dropdown arrow icons
        let textNode = Array.from(selectedEl.childNodes).find(n => n.nodeType === Node.TEXT_NODE && n.nodeValue.trim().length > 0);
        if (textNode) textNode.nodeValue = displayValue;
        else selectedEl.innerText = displayValue;
    }
};

function setActiveCell(cell) {
    if (activeCell) activeCell.classList.remove('cell-active');
    activeCell = cell;
    if (activeCell) {
        activeCell.classList.add('cell-active');
        const rowIdx = activeCell.parentElement.rowIndex;
        const colIdx = activeCell.cellIndex - 1;
        const refEl = document.getElementById('activeCellRef');
        const formulaEl = document.getElementById('formulaInput');
        
        if (refEl) refEl.innerText = `${numToCol(colIdx)}${rowIdx}`;
        
        // Show stored formula or empty
        const storedFormula = cellFormulas.get(activeCell) || '';
        if (formulaEl) {
            formulaEl.value = storedFormula;
            formulaEl.placeholder = storedFormula ? '' : 'Enter formula (e.g., =SUM(A1:A5))';
        }
        
        // Update value display
        updateValueDisplayForCell(activeCell);
        
        // Formatting toolbar (unchanged)
        const style = window.getComputedStyle(activeCell);
        let currentFont = activeCell.style.fontFamily || style.fontFamily || 'Inter';
        updateDropdownUI('fontDropdown', currentFont.split(',')[0].replace(/['"]/g, '').trim());
        let currentSize = activeCell.style.fontSize || style.fontSize || '14px';
        const sizeInput = document.getElementById('customSizeInput');
        if (sizeInput) sizeInput.value = parseInt(currentSize) || 14;
        const btnBold = document.querySelector('[data-cmd="bold"]');
        const btnItalic = document.querySelector('[data-cmd="italic"]');
        const btnUnderline = document.querySelector('[data-cmd="underline"]');
        if (btnBold) btnBold.classList.toggle('active-format', style.fontWeight === 'bold' || style.fontWeight === '700');
        if (btnItalic) btnItalic.classList.toggle('active-format', style.fontStyle === 'italic');
        if (btnUnderline) {
            const isUnderline = style.textDecoration.includes('underline');
            const isDouble = style.textDecoration.includes('double');
            btnUnderline.classList.toggle('active-format', isUnderline);
            if (isDouble) btnUnderline.style.borderBottom = "3px double #1e6f3f";
            else if (isUnderline) btnUnderline.style.borderBottom = "3px solid #1e6f3f";
            else btnUnderline.style.borderBottom = "none";
        }
    } else {
        const refEl = document.getElementById('activeCellRef');
        const formulaEl = document.getElementById('formulaInput');
        if (refEl) refEl.innerText = '';
        if (formulaEl) formulaEl.value = '';
        if (valueDisplay) valueDisplay.value = '';
    }
}

function updateValueDisplayForCell(cell) {
    if (!valueDisplay) return;
    const formula = cellFormulas.get(cell);
    if (formula && formula.startsWith('=')) {
        const result = evaluateFormula(formula, getCellValueFromDOM);
        if (result !== null && !isNaN(result)) {
            valueDisplay.value = result;
        } else {
            // If evaluation fails (e.g., unsupported function like IF, SQRT),
            // show the cell's current computed value (already in the DOM).
            valueDisplay.value = cell.innerText.trim() || '(empty)';
        }
    } else {
        valueDisplay.value = cell.innerText.trim() || '(empty)';
    }
}

function attachCellEvents() {
    document.querySelectorAll('.tool-btn, .custom-dropdown, .color-swatch').forEach(el => {
        el.addEventListener('mousedown', (e) => {
            if (e.target.tagName !== 'INPUT') e.preventDefault();
        });
    });

    document.querySelectorAll('.editable-cell').forEach(cell => {
        cell.onfocus = () => setActiveCell(cell);
        cell.onblur = () => {
    captureState();
    if (activeCell === cell) {
        // If cell was manually edited, remove formula if it became plain text
        const currentValue = cell.innerText.trim();
        const storedFormula = cellFormulas.get(cell);
        if (!currentValue.startsWith('=') && storedFormula) {
            cellFormulas.delete(cell);
        }
        updateValueDisplayForCell(cell);
    }
};
    });
}

function updateCellFromFormulaBar() {
    if (!activeCell) return;
    const formulaInput = document.getElementById('formulaInput');
    const newValue = formulaInput.value;
    if (newValue.startsWith('=')) {
        cellFormulas.set(activeCell, newValue);
        const result = evaluateFormula(newValue, getCellValueFromDOM);
        activeCell.innerText = (result !== null && !isNaN(result)) ? result : newValue;
    } else {
        cellFormulas.delete(activeCell);
        activeCell.innerText = newValue;
    }
    updateValueDisplayForCell(activeCell);
    captureState();
}

// Formula Bar Listeners
const fBar = document.getElementById('formulaInput');
if (fBar) {
    fBar.addEventListener('change', updateCellFromFormulaBar);
    fBar.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            updateCellFromFormulaBar();
            activeCell?.blur();
        }
    });
}

// Helper to insert text at cursor position in the formula input
function insertAtCursor(input, text) {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const value = input.value;
    input.value = value.slice(0, start) + text + value.slice(end);
    input.selectionStart = input.selectionEnd = start + text.length;
    input.focus();
}

// Listen for clicks on any cell while formula input is focused
const formulaInput = document.getElementById('formulaInput');
if (formulaInput) {
    document.addEventListener('click', (e) => {
        // If the clicked element is an editable cell AND the formula input has focus
        if (e.target.classList && e.target.classList.contains('editable-cell') && document.activeElement === formulaInput) {
            e.preventDefault();
            // Get cell reference (e.g., "A1")
            const row = e.target.parentElement.rowIndex;
            const col = e.target.cellIndex - 1;
            const ref = numToCol(col) + row;
            insertAtCursor(formulaInput, ref);
        }
    });
}

// Function Buttons (SUM, MIN, etc)
document.querySelectorAll('.func-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (!activeCell) return;
        const func = btn.getAttribute('data-func');
        const rowIdx = activeCell.parentElement.rowIndex;
        const colIdx = numToCol(activeCell.cellIndex - 1);
        const formula = `=${func.toUpperCase()}(${colIdx}1:${colIdx}${rowIdx > 1 ? rowIdx - 1 : 1})`;
        const fInput = document.getElementById('formulaInput');
        if (fInput) {
            fInput.value = formula;
            updateCellFromFormulaBar();
        }
    });
});

/// ==========================================
// 5. FORMATTING TOOLBAR & COLORS
// ==========================================
function setupFormattingToolbar() {
    document.querySelectorAll('.custom-dropdown').forEach(dropdown => {
        const selected = dropdown.querySelector('.dropdown-selected');
        if (selected) {
            selected.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.custom-dropdown').forEach(d => { if (d !== dropdown) d.classList.remove('active'); });
                dropdown.classList.toggle('active');
            });
        }
    });

    document.addEventListener('click', () => {
        document.querySelectorAll('.custom-dropdown').forEach(d => d.classList.remove('active'));
    });

    function applyFormat(property, value) {
        if (!activeCell) return;
        
        if (property === 'fontSize' && !String(value).includes('px')) {
            value = parseInt(value) + 'px';
        }

        activeCell.style[property] = value;
        
        if (property === 'fontFamily') {
            updateDropdownUI('fontDropdown', value.split(',')[0].replace(/['"]/g, '').trim());
        } else if (property === 'fontSize') {
            const sizeInput = document.getElementById('customSizeInput');
            if (sizeInput) sizeInput.value = parseInt(value) || 14;
            else updateDropdownUI('sizeDropdown', parseInt(value));
        }
        
        captureState();
    }

    const sizeInput = document.getElementById('customSizeInput');
    if (sizeInput) {
        sizeInput.addEventListener('click', (e) => { e.stopPropagation(); sizeInput.select(); });
        sizeInput.addEventListener('change', function() {
            applyFormat('fontSize', this.value);
        });
    }

    function setupDropdownItems(dropdownId, styleProperty) {
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;

        let trueOriginal = '';

        dropdown.addEventListener('mousedown', () => {
            if (activeCell && !dropdown.classList.contains('active')) {
                trueOriginal = activeCell.style[styleProperty];
            }
        });

        dropdown.querySelectorAll('[data-val]').forEach(item => {
            item.addEventListener('mouseenter', function() { 
                if (activeCell) {
                    let val = this.getAttribute('data-val');
                    if (styleProperty === 'fontSize' && !val.includes('px')) val += 'px';
                    activeCell.style[styleProperty] = val; 
                }
            });
            
            item.addEventListener('mouseleave', function() { 
                // Revert to what the cell was before the dropdown even opened
                if (activeCell) activeCell.style[styleProperty] = trueOriginal; 
            });
            
            item.addEventListener('click', function(e) {
                e.stopPropagation(); 
                if (!activeCell) return;
                
                let val = this.getAttribute('data-val');
                if (styleProperty === 'fontSize' && !val.includes('px')) val += 'px';
                
                trueOriginal = val; // Lock this as the new baseline so mouseleave doesn't erase it
                applyFormat(styleProperty, val);
                
                dropdown.classList.remove('active');
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

            if (cmd === 'bold') {
                const isBold = activeCell.style.fontWeight === 'bold' || activeCell.style.fontWeight === '700';
                activeCell.style.fontWeight = isBold ? 'normal' : 'bold';
                this.classList.toggle('active-format', !isBold);
            } 
            else if (cmd === 'italic') {
                const isItalic = activeCell.style.fontStyle === 'italic';
                activeCell.style.fontStyle = isItalic ? 'normal' : 'italic';
                this.classList.toggle('active-format', !isItalic);
            } 
            else if (cmd === 'underline') {
                const currentDeco = activeCell.style.textDecoration;
                
                if (currentDeco.includes('underline double')) {
                    // It's double. Turn it completely off.
                    activeCell.style.textDecoration = 'none';
                    this.classList.remove('active-format');
                    this.style.borderBottom = "none";
                } else if (currentDeco.includes('underline')) {
                    // It's single. Upgrade to double!
                    activeCell.style.textDecoration = 'underline double';
                    this.classList.add('active-format');
                    this.style.borderBottom = "3px double #1e6f3f";
                } else {
                    // It's off. Turn on single.
                    activeCell.style.textDecoration = 'underline';
                    this.classList.add('active-format');
                    this.style.borderBottom = "3px solid #1e6f3f";
                }
            }
            captureState();
        });
    });

    // 5. Colors
    const excelColors = [
        '#ffffff', '#000000', '#eeece1', '#1f497d', '#4f81bd', '#c0504d',
        '#f2f2f2', '#808080', '#ddd9c3', '#c6d9f1', '#dbe5f1', '#f2dcdb',
        '#d9d9d9', '#595959', '#c4bd97', '#8db4e2', '#b8cce4', '#e6b8b7',
        '#bfbfbf', '#404040', '#938953', '#548dd4', '#95b3d7', '#d99694',
        '#ff0000', '#00ff00', '#0000ff', '#ffff00', '#00ffff', '#ff00ff'
    ];

    window.applyColor = (color, isText) => {
        if (!activeCell) return;
        activeCell.style[isText ? 'color' : 'backgroundColor'] = color;
        const ind = document.querySelector(`#${isText ? 'textColorDropdown' : 'fillColorDropdown'} .color-indicator`);
        if (ind) ind.style.backgroundColor = color;
        captureState();
    };

    function buildPalette(gridId, isText) {
        const grid = document.getElementById(gridId);
        const dropdown = grid?.closest('.custom-dropdown');
        if (!grid || !dropdown) return;
        
        let trueOriginalColor = '';

        dropdown.addEventListener('mousedown', () => {
            if (activeCell && !dropdown.classList.contains('active')) {
                trueOriginalColor = activeCell.style[isText ? 'color' : 'backgroundColor'];
            }
        });

        excelColors.forEach(color => {
            const swatch = document.createElement('div');
            swatch.className = 'color-swatch'; swatch.style.backgroundColor = color;
            
            swatch.addEventListener('mouseenter', () => {
                if(activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = color;
            });
            swatch.addEventListener('mouseleave', () => {
                if(activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = trueOriginalColor;
            });
            swatch.addEventListener('click', (e) => {
                e.stopPropagation();
                if(activeCell) {
                    trueOriginalColor = color;
                    applyColor(color, isText);
                    dropdown.classList.remove('active');
                }
            });
            
            grid.appendChild(swatch);
        });
    }
    buildPalette('fillPaletteGrid', false);
    buildPalette('textPaletteGrid', true);

    const nFill = document.getElementById('nativeFillPicker');
    const nText = document.getElementById('nativeTextPicker');
    if (nFill) nFill.oninput = (e) => applyColor(e.target.value, false);
    if (nText) nText.oninput = (e) => applyColor(e.target.value, true);
}
// ==========================================
// 6. ROW/COLUMN OPERATIONS
// ==========================================
function addRow() {
    const tbody = document.getElementById('tableBody');
    const colCount = document.querySelectorAll('#headerRow th:not(.row-header-cell)').length;
    const tr = document.createElement('tr');
    let html = `<td class="row-header-cell"><span style="font-size:0.7rem;">${tbody.children.length + 1}</span><button class="row-delete-btn" onclick="deleteRowHandler(this)"><i class="fas fa-trash-alt"></i></button></td>`;
    for (let i = 0; i < colCount; i++) html += `<td contenteditable="true" class="editable-cell"></td>`;
    tr.innerHTML = html;
    tbody.appendChild(tr);
    attachCellEvents(); updateStatusBar(); renumberRows(); captureState();
}

function deleteRowHandler(btn) {
    if (document.querySelectorAll('#tableBody tr').length <= 1) return alert("Min 1 row required");
    btn.closest('tr').remove();
    updateStatusBar(); renumberRows(); captureState();
}

function addColumn() {
    const headerRow = document.getElementById('headerRow');
    const newTh = document.createElement('th');
    newTh.className = 'header-custom';
    let opts = '';
    const sample = document.querySelector('.mapping-select');
    if (sample) sample.querySelectorAll('option').forEach(o => { opts += `<option value="${o.value}">${o.textContent}</option>`; });
    newTh.innerHTML = `<div class="header-content"><button class="del-col" onclick="deleteColumnHandler(this)"><i class="fas fa-times"></i></button><span class="header-label" contenteditable="true">New</span><select class="mapping-select" onchange="handleMappingChange(this)">${opts}</select></div>`;
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
    document.querySelectorAll('#tableBody tr').forEach(row => row.deleteCell(idx));
    updateStatusBar(); captureState();
}

function renumberRows() {
    document.querySelectorAll('#tableBody tr').forEach((row, i) => {
        const s = row.querySelector('.row-header-cell span');
        if (s) s.innerText = i + 1;
    });
}
window.deleteRowHandler = deleteRowHandler;
window.deleteColumnHandler = deleteColumnHandler;
window.handleMappingChange = (sel) => {
    sel.closest('th').className = sel.value ? 'header-matched' : 'header-custom';
    captureState();
};

// ==========================================
// 7. KEYBOARD NAVIGATION
// ==========================================
function attachKeyboardNavigation() {
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
        if ((e.ctrlKey || e.metaKey) && e.key === 'y') { e.preventDefault(); redo(); }
        if (!activeCell) return;

        const row = activeCell.parentElement;
        const tbody = document.getElementById('tableBody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const rIdx = rows.indexOf(row);
        const cells = Array.from(row.querySelectorAll('td.editable-cell'));
        const cIdx = cells.indexOf(activeCell);

        if (e.key === 'ArrowUp' && rIdx > 0) { e.preventDefault(); rows[rIdx - 1].cells[cIdx + 1].focus(); }
        else if (e.key === 'ArrowDown' && rIdx < rows.length - 1) { e.preventDefault(); rows[rIdx + 1].cells[cIdx + 1].focus(); }
        else if (e.key === 'ArrowLeft' && cIdx > 0) { e.preventDefault(); cells[cIdx - 1].focus(); }
        else if (e.key === 'ArrowRight' && cIdx < cells.length - 1) { e.preventDefault(); cells[cIdx + 1].focus(); }
        else if (e.key === 'Enter') { e.preventDefault(); updateCellFromFormulaBar(); rows[rIdx + 1]?.cells[cIdx + 1]?.focus(); }
    });
}

// ==========================================
// 8. SAVE WORKBOOK
// ==========================================
async function saveData() {
    const btn = document.getElementById('saveProcessBtn');
    if (!btn) return;
    const oldHtml = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> Saving...';
    btn.disabled = true;

    try {
        const headers = []; const colIndices = []; const mappings = {};
        
        document.querySelectorAll('#headerRow th:not(.row-header-cell)').forEach((th, idx) => {
            const isTemp = th.classList.contains('header-template-only');
            const sel = th.querySelector('.mapping-select');
            const mapped = sel && sel.value !== "";
            const labelEl = th.querySelector('.header-label');
            const text = labelEl ? labelEl.innerText.trim() : "";
            
            if (!isTemp || mapped) {
                colIndices.push(idx);
                headers.push(mapped ? sel.value : text);
                if (mapped) mappings[text] = sel.value;
            }
        });

        const rows = [];
        document.querySelectorAll('#tableBody tr').forEach(tr => {
            const rowData = []; 
            const tds = tr.querySelectorAll('td.editable-cell');
            
            colIndices.forEach(idx => {
                const c = tds[idx];
                
                if (!c) {
                    rowData.push({ value: "" });
                    return;
                }

                let currentUnderline = null;
                const decoration = c.style.textDecoration || "";
                if (decoration.includes("underline double")) currentUnderline = "double";
                else if (decoration.includes("underline")) currentUnderline = "single";

                rowData.push({
                    value: c.innerText.trim(),
                    bold: c.style.fontWeight === "bold" || c.style.fontWeight === "700",
                    italic: c.style.fontStyle === "italic",
                    underline: currentUnderline,
                    color: c.style.color || null,
                    bg: c.style.backgroundColor || null,
                    fontFamily: c.style.fontFamily || null,
                    fontSize: c.style.fontSize || null
                });
            });
            rows.push(rowData);
        });

        const payload = { headers, rows, mappings };
        console.log("🚀 STEP 1 (JS OUT): Sending this payload to Python ->", payload);
        console.log("🚀 STEP 1a (JS OUT - Check Row 1):", rows[0]);

        const res = await fetch(window.DJANGO_VARS.saveUrl, {
            method: "POST", 
            headers: { "Content-Type": "application/json", "X-CSRFToken": window.DJANGO_VARS.csrfToken },
            body: JSON.stringify({ headers, rows, mappings })
        });
        
        const data = await res.json();
        if (res.ok) {
            showToast("Saved!", "success");
            setTimeout(() => {
                const newId = data.new_file_id;
                window.location.href = window.DJANGO_VARS.uploadUrl + "?preview_id=" + newId + "&_=" + Date.now();
            }, 800); 
        } else { 
            showToast("Error: " + data.error, "error"); 
        }
    } catch (e) { 
        console.error("Save failed:", e);
        showToast("Connection error", "error"); 
    } finally { 
        btn.innerHTML = oldHtml; 
        btn.disabled = false; 
    }
}

function showToast(msg, type) {
    let t = document.createElement('div'); t.innerText = msg;
    t.style.cssText = `position:fixed; bottom:70px; right:30px; background:${type === 'success' ? '#1e6f3f' : '#d13438'}; color:white; padding:12px 24px; border-radius:40px; z-index:9999;`;
    document.body.appendChild(t); setTimeout(() => t.remove(), 2500);
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

    const uiBtns = { 'addRowBtn': addRow, 'addColBtn': addColumn, 'undoBtn': undo, 'redoBtn': redo, 'saveProcessBtn': saveData };
    Object.entries(uiBtns).forEach(([id, fn]) => { const el = document.getElementById(id); if (el) el.onclick = fn; });

    // --- Restore saved mappings (unchanged) ---
    let saved = window.DJANGO_VARS.savedMappings;
    while (typeof saved === 'string') {
        try { saved = JSON.parse(saved); } catch(e) { break; }
    }
    if (saved && typeof saved === 'object') {
        document.querySelectorAll('#headerRow th:not(.row-header-cell)').forEach(th => {
            const label = th.querySelector('.header-label')?.innerText.trim();
            if (saved[label]) {
                const s = th.querySelector('.mapping-select');
                if (s) { s.value = saved[label]; handleMappingChange(s); }
            }
        });
    }

    // --- Restore styles (unchanged) ---
    let styles = window.DJANGO_VARS.styleData;
    while (typeof styles === 'string') {
        try { styles = JSON.parse(styles); } catch(e) { break; }
    }
    if (styles && Array.isArray(styles)) {
        const trs = document.querySelectorAll('#tableBody tr');
        styles.forEach((row, ri) => {
            if (trs[ri]) {
                const tds = trs[ri].querySelectorAll('td.editable-cell');
                row.forEach((c, ci) => {
                    if (tds[ci]) {
                        if (c.bold) tds[ci].style.fontWeight = 'bold';
                        if (c.italic) tds[ci].style.fontStyle = 'italic';
                        if (c.underline === 'double') tds[ci].style.textDecoration = 'underline double';
                        else if (c.underline === 'single' || c.underline === true) tds[ci].style.textDecoration = 'underline';
                        if (c.color) tds[ci].style.color = c.color;
                        if (c.bg) tds[ci].style.backgroundColor = c.bg;
                        if (c.fontFamily) tds[ci].style.fontFamily = c.fontFamily;
                        if (c.fontSize) tds[ci].style.fontSize = c.fontSize;
                    }
                });
            }
        });
    }

    // ========== NEW: RESTORE FORMULAS ==========
    let formulas = window.DJANGO_VARS.formulasData;
    while (typeof formulas === 'string') {
        try { formulas = JSON.parse(formulas); } catch(e) { break; }
    }
    if (formulas && Array.isArray(formulas)) {
        const trs = document.querySelectorAll('#tableBody tr');
        formulas.forEach((row, ri) => {
            if (trs[ri]) {
                const tds = trs[ri].querySelectorAll('td.editable-cell');
                row.forEach((formula, ci) => {
                    if (formula && tds[ci] && typeof formula === 'string' && formula.startsWith('=')) {
                        cellFormulas.set(tds[ci], formula);
                    }
                });
            }
        });
    }
    if (activeCell) updateValueDisplayForCell(activeCell);

    captureState();

    console.log("🔄 STEP 5 (JS IN): Page loaded. What did Django give us?");
    console.log("Raw DJANGO_VARS.styleData type:", typeof window.DJANGO_VARS.styleData);
    console.log("Raw DJANGO_VARS.styleData value:", window.DJANGO_VARS.styleData);
    console.log("Parsed styles variable:", styles);
}

init();