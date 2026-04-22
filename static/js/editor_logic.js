// ==========================================
// 1. GLOBAL VARIABLES & STATE
// ==========================================
let historyStack = [];
let redoStack = [];
let activeCell = null;
let selectedCells = []; // array of DOM cells currently selected (excluding activeCell)
let cellFormulas = new Map();
let lastStateJson = null;
let originalState = { fontFamily: '', fontSize: '', backgroundColor: '', color: '' };
let isRestoring = false;
let valueDisplay = document.getElementById('valueDisplay');
let isDragging = false;
let dragStartCell = null;
let lastDragCell = null;

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
        const rowHeaderCell = headerRow.querySelector('.row-header-cell');
        let newHeaderHtml = rowHeaderCell ? rowHeaderCell.outerHTML : '';
        state.headers.forEach(h => { newHeaderHtml += h.outerHTML; });
        headerRow.innerHTML = newHeaderHtml;

        const selects = headerRow.querySelectorAll('.mapping-select');
        const labels = headerRow.querySelectorAll('.header-label');
        state.headers.forEach((h, idx) => {
            if (selects[idx]) selects[idx].value = h.selectedValue;
            if (labels[idx]) labels[idx].innerText = h.text;
            const th = selects[idx]?.closest('th');
            if (th) th.className = h.selectedValue ? 'header-matched' : 'header-custom';
        });

        const tbody = document.getElementById('tableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        cellFormulas.clear();

        state.rows.forEach((row, ri) => {
            const tr = document.createElement('tr');
            let html = `<td class="row-header-cell"><span style="font-size:0.7rem;">${ri+1}</span><button class="row-delete-btn" onclick="deleteRowHandler(this)"><i class="fas fa-trash-alt"></i></button></td>`;
            row.forEach(cellData => {
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

        attachCellEvents();
        updateStatusBar();
        renumberRows();
        lastStateJson = JSON.stringify(state);
        activeCell = null;
        clearSelection();
    } catch (e) {
        console.error("Critical error during Undo restoration:", e);
    } finally {
        setTimeout(() => { isRestoring = false; }, 10);
    }
}

function undo() {
    if (historyStack.length < 2) return;
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
    return str.replace(/[&<>]/g, m => m === '&' ? '&amp;' : (m === '<' ? '&lt;' : '&gt;'));
}
function markdownToHtml(text) {
    if (!text) return '';
    var html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold italic, bold, italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Inline code
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');

    // Unordered lists
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>(<h[234]>)/g, '$1');
    html = html.replace(/(<\/h[234]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');

    // Line breaks
    html = html.replace(/(?<!<\/li>)(?<!<\/ul>)(?<!<\/h[234]>)\n(?!<)/g, '<br>');

    return html;
}

// ==========================================
// 3. ENHANCED FORMULA EVALUATION (with IF, COUNTIF, COUNTA, XLOOKUP, VLOOKUP)
// ==========================================
function evaluateFormula(formula, getCellValue) {
    if (!formula.startsWith('=')) return null;
    const expr = formula.substring(1).trim();

    const funcMatch = expr.match(/^([A-Z_]+)\((.*)\)$/i);
    if (funcMatch) {
        const func = funcMatch[1].toUpperCase();
        const argsString = funcMatch[2];
        const args = parseArguments(argsString);
        
        if (['SUM', 'AVERAGE', 'COUNT', 'MAX', 'MIN'].includes(func)) {
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
            if (func === 'SUM') return allValues.reduce((a,b)=>a+b,0);
            if (func === 'AVERAGE') return allValues.length ? allValues.reduce((a,b)=>a+b,0)/allValues.length : 0;
            if (func === 'COUNT') return allValues.length;
            if (func === 'MAX') return allValues.length ? Math.max(...allValues) : 0;
            if (func === 'MIN') return allValues.length ? Math.min(...allValues) : 0;
        }
        
        if (func === 'IF') {
            if (args.length < 2) return '#ERROR';
            let condition = args[0];
            let trueVal = args[1];
            let falseVal = args.length > 2 ? args[2] : '';
            let condResult;
            try {
                let condExpr = condition.replace(/[A-Z]+[0-9]+/gi, (ref) => {
                    let val = getCellValue(ref);
                    return isNaN(val) ? `"${val}"` : val;
                });
                condResult = Function('"use strict";return (' + condExpr + ')')();
            } catch(e) { condResult = false; }
            if (condResult) {
                if (trueVal.match(/[A-Z]+[0-9]+/)) {
                    let val = getCellValue(trueVal);
                    return val !== null ? val : trueVal;
                }
                return trueVal;
            } else {
                if (falseVal.match(/[A-Z]+[0-9]+/)) {
                    let val = getCellValue(falseVal);
                    return val !== null ? val : falseVal;
                }
                return falseVal;
            }
        }
        
        if (func === 'COUNTIF') {
            if (args.length < 2) return '#ERROR';
            let range = args[0];
            let criteria = args[1];
            let cells = getCellsInRange(range, getCellValue);
            let count = 0;
            for (let cell of cells) {
                let val = getCellValue(cell);
                let match = false;
                if (criteria.startsWith('>') || criteria.startsWith('<') || criteria.startsWith('=')) {
                    let op = criteria.match(/[<>]=?/)[0];
                    let target = parseFloat(criteria.slice(op.length));
                    let num = parseFloat(val);
                    if (isNaN(num)) continue;
                    if (op === '>' && num > target) match = true;
                    else if (op === '<' && num < target) match = true;
                    else if (op === '>=' && num >= target) match = true;
                    else if (op === '<=' && num <= target) match = true;
                    else if (op === '=' && num == target) match = true;
                } else {
                    match = (val == criteria);
                }
                if (match) count++;
            }
            return count;
        }
        
        if (func === 'COUNTA') {
            if (args.length < 1) return '#ERROR';
            let range = args[0];
            let cells = getCellsInRange(range, getCellValue);
            let count = 0;
            for (let cell of cells) {
                let val = getCellValue(cell);
                if (val !== null && val !== "") count++;
            }
            return count;
        }
        
        if (func === 'XLOOKUP') {
            if (args.length < 3) return '#ERROR';
            let lookupValue = args[0];
            let lookupArray = args[1];
            let returnArray = args[2];
            let ifNotFound = args.length > 3 ? args[3] : '#N/A';
            let lookupCells = getCellsInRange(lookupArray, getCellValue);
            let returnCells = getCellsInRange(returnArray, getCellValue);
            for (let i = 0; i < lookupCells.length; i++) {
                let val = getCellValue(lookupCells[i]);
                if (val == lookupValue) {
                    let retVal = getCellValue(returnCells[i]);
                    return retVal !== null ? retVal : '#N/A';
                }
            }
            return ifNotFound;
        }
        
        if (func === 'VLOOKUP') {
            if (args.length < 3) return '#ERROR';
            let lookupValue = args[0];
            let tableArray = args[1];
            let colIndex = parseInt(args[2]);
            let rangeLookup = args.length > 3 ? args[3] : 'TRUE';
            let tableCells = getCellsInRange(tableArray, getCellValue);
            let rows = tableCells.length / getColumnCount(tableArray);
            for (let i = 0; i < rows; i++) {
                let cellRef = tableCells[i];
                let val = getCellValue(cellRef);
                if (val == lookupValue) {
                    let targetCellRef = tableCells[i + (colIndex-1)*rows];
                    let retVal = getCellValue(targetCellRef);
                    return retVal !== null ? retVal : '#N/A';
                }
            }
            return '#N/A';
        }
        
        return '#NAME?';
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
    let args = [], current = '', depth = 0;
    for (let ch of argsString) {
        if (ch === '(') depth++;
        if (ch === ')') depth--;
        if (ch === ',' && depth === 0) {
            args.push(current.trim());
            current = '';
        } else { current += ch; }
    }
    if (current.trim()) args.push(current.trim());
    return args;
}

function getRangeValues(start, end, getCellValue) {
    const startCol = start.match(/[A-Z]+/)[0];
    const startRow = parseInt(start.match(/[0-9]+/)[0]);
    const endCol = end.match(/[A-Z]+/)[0];
    const endRow = parseInt(end.match(/[0-9]+/)[0]);
    const values = [];
    const startColNum = colToNum(startCol);
    const endColNum = colToNum(endCol);
    for (let r = startRow; r <= endRow; r++) {
        for (let c = startColNum; c <= endColNum; c++) {
            let val = getCellValue(numToCol(c) + r);
            if (!isNaN(val) && val !== "" && val !== null) values.push(Number(val));
        }
    }
    return values;
}

function getCellsInRange(range, getCellValue) {
    let cells = [];
    if (range.includes(':')) {
        let [start, end] = range.split(':');
        const startCol = start.match(/[A-Z]+/)[0];
        const startRow = parseInt(start.match(/[0-9]+/)[0]);
        const endCol = end.match(/[A-Z]+/)[0];
        const endRow = parseInt(end.match(/[0-9]+/)[0]);
        const startColNum = colToNum(startCol);
        const endColNum = colToNum(endCol);
        for (let r = startRow; r <= endRow; r++) {
            for (let c = startColNum; c <= endColNum; c++) {
                cells.push(numToCol(c) + r);
            }
        }
    } else {
        cells.push(range);
    }
    return cells;
}

function getColumnCount(range) {
    let [start, end] = range.split(':');
    const startCol = start.match(/[A-Z]+/)[0];
    const endCol = end.match(/[A-Z]+/)[0];
    return colToNum(endCol) - colToNum(startCol) + 1;
}

function colToNum(col) {
    let num = 0;
    for (let i = 0; i < col.length; i++) num = num * 26 + (col.charCodeAt(i) - 64);
    return num - 1;
}
function numToCol(num) {
    let col = "";
    while (num >= 0) {
        col = String.fromCharCode(65 + (num % 26)) + col;
        num = Math.floor(num / 26) - 1;
    }
    return col;
}

// ===== FORMULA TEMPLATES FOR HINTS =====
const formulaTemplates = {
    "SUM": { syntax: "=SUM(range)", ex: "Example: =SUM(A1:A10)" },
    "AVERAGE": { syntax: "=AVERAGE(range)", ex: "Example: =AVERAGE(B1:B20)" },
    "COUNT": { syntax: "=COUNT(range)", ex: "Example: =COUNT(C1:C15)" },
    "COUNTA": { syntax: "=COUNTA(range)", ex: "Example: =COUNTA(B1:B4)" },
    "MAX": { syntax: "=MAX(range)", ex: "Example: =MAX(E1:E50)" },
    "MIN": { syntax: "=MIN(range)", ex: "Example: =MIN(F1:F50)" },
    "IF": { syntax: "=IF(cond, true, false)", ex: 'Example: =IF(A1>50, "Pass", "Fail")' },
    "COUNTIF": { syntax: '=COUNTIF(range, "crit")', ex: 'Example: =COUNTIF(A1:A30, ">90")' },
    "VLOOKUP": { syntax: "=VLOOKUP(val, table, col)", ex: 'Example: =VLOOKUP("Apple", A1:C10, 2)' },
    "XLOOKUP": { syntax: "=XLOOKUP(val, search, return)", ex: "Example: =XLOOKUP(D1, A1:A10, B1:B10)" }
};

// ===== SHOW FORMULA HINT =====
window.showFormulaHint = function(typedText) {
    const hintBox = document.getElementById("formulaHint");
    if (!hintBox) return;
    
    if (!typedText || !typedText.startsWith("=")) {
        hintBox.style.display = "none";
        hintBox.innerHTML = "";
        return;
    }
    
    let upperText = typedText.toUpperCase().trim();
    // Sort keys by length descending so "COUNTA" matches before "COUNT"
    let foundKey = null;
    const sortedKeys = Object.keys(formulaTemplates).sort((a,b) => b.length - a.length);
    for (let key of sortedKeys) {
        if (upperText.startsWith("=" + key)) {
            foundKey = key;
            break;
        }
    }
    
    if (foundKey) {
        const template = formulaTemplates[foundKey];
        hintBox.innerHTML = `<span style="color: #2c7be5;">${template.syntax}</span> | <span style="color: #6c757d; font-style: italic;">${template.ex}</span>`;
        hintBox.style.display = "block";
    } else {
        hintBox.style.display = "none";
        hintBox.innerHTML = "";
    }
};

function getSmartRange(cell) {
    const table = document.getElementById('tableBody');
    const rows = Array.from(table.rows);
    const cellIndex = cell.cellIndex;
    const rowIndex = cell.parentElement.rowIndex - 1;

    const hasValue = (r, c) => {
        if (!rows[r] || !rows[r].cells[c]) return false;
        let val = rows[r].cells[c].innerText.trim();
        return val !== "";
    };

    // Vertical: cells above and below (excluding active cell)
    let topRow = rowIndex - 1;
    let hasAbove = false;
    while (topRow >= 0 && hasValue(topRow, cellIndex)) {
        hasAbove = true;
        topRow--;
    }
    let bottomRow = rowIndex + 1;
    let hasBelow = false;
    while (bottomRow < rows.length && hasValue(bottomRow, cellIndex)) {
        hasBelow = true;
        bottomRow++;
    }
    if (hasAbove || hasBelow) {
        let startRow = hasAbove ? topRow + 1 : rowIndex + 1;
        let endRow = hasBelow ? bottomRow - 1 : rowIndex - 1;
        if (startRow <= endRow) {
            return `${numToCol(cellIndex - 1)}${startRow + 1}:${numToCol(cellIndex - 1)}${endRow + 1}`;
        }
    }

    // Horizontal: cells left and right (excluding active cell)
    let leftCol = cellIndex - 1;
    let hasLeft = false;
    while (leftCol >= 1 && hasValue(rowIndex, leftCol)) {
        hasLeft = true;
        leftCol--;
    }
    let rightCol = cellIndex + 1;
    let hasRight = false;
    const maxCol = rows[0] ? rows[0].cells.length - 1 : cellIndex;
    while (rightCol <= maxCol && hasValue(rowIndex, rightCol)) {
        hasRight = true;
        rightCol++;
    }
    if (hasLeft || hasRight) {
        let startCol = hasLeft ? leftCol + 1 : cellIndex + 1;
        let endCol = hasRight ? rightCol - 1 : cellIndex - 1;
        if (startCol <= endCol) {
            return `${numToCol(startCol - 1)}${rowIndex + 1}:${numToCol(endCol - 1)}${rowIndex + 1}`;
        }
    }

    return "";
}

// ==========================================
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
    const colIndex = colToNum(match[1]);
    const rowIndex = parseInt(match[2]) - 1;
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
        const storedFormula = cellFormulas.get(activeCell) || '';
        if (formulaEl) {
            formulaEl.value = storedFormula;
            formulaEl.placeholder = storedFormula ? '' : 'Enter formula (e.g., =SUM(A1:A5))';
        }
        if (typeof window.showFormulaHint === 'function') {
            window.showFormulaHint(formulaEl ? formulaEl.value : '');
        }
        updateValueDisplayForCell(activeCell);
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
        if (typeof window.showFormulaHint === 'function') {
        window.showFormulaHint('');
    }
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
            valueDisplay.value = cell.innerText.trim() || '(empty)';
        }
    } else {
        valueDisplay.value = cell.innerText.trim() || '(empty)';
    }
}

// --- Multi-cell selection helpers ---
function clearSelection() {
    selectedCells.forEach(cell => {
        cell.classList.remove('range-selected');
    });
    selectedCells = [];
}

function addToSelection(cell) {
    if (!selectedCells.includes(cell)) {
        selectedCells.push(cell);
        cell.classList.add('range-selected');
    }
}

function selectRange(startCell, endCell) {
    clearSelection();
    if (!startCell || !endCell) return;
    
    const startRow = startCell.parentElement.rowIndex;
    const startCol = startCell.cellIndex;
    const endRow = endCell.parentElement.rowIndex;
    const endCol = endCell.cellIndex;
    
    const minRow = Math.min(startRow, endRow);
    const maxRow = Math.max(startRow, endRow);
    const minCol = Math.min(startCol, endCol);
    const maxCol = Math.max(startCol, endCol);
    
    const tbody = document.getElementById('tableBody');
    for (let r = minRow; r <= maxRow; r++) {
        const row = tbody.rows[r];
        if (!row) continue;
        for (let c = minCol; c <= maxCol; c++) {
            const cell = row.cells[c];
            if (cell && cell.classList && cell.classList.contains('editable-cell')) {
                selectedCells.push(cell);
                cell.classList.add('range-selected');
            }
        }
    }
}

function applyFormatToSelection(property, value) {
    let cellsToFormat = [...selectedCells];
    if (activeCell && !cellsToFormat.includes(activeCell)) {
        cellsToFormat.push(activeCell);
    }
    if (cellsToFormat.length === 0) return;
    
    for (let cell of cellsToFormat) {
        if (property === 'fontSize' && !String(value).includes('px')) {
            cell.style[property] = parseInt(value) + 'px';
        } else {
            cell.style[property] = value;
        }
    }
    captureState();
    if (activeCell) setActiveCell(activeCell);
    
}

function attachCellEvents() {
    document.querySelectorAll('.tool-btn, .custom-dropdown, .color-swatch').forEach(el => {
        el.addEventListener('mousedown', (e) => {
            if (e.target.tagName !== 'INPUT') e.preventDefault();
        });
    });
    
    document.querySelectorAll('.editable-cell').forEach(cell => {
        cell.removeEventListener('mousedown', cell._dragStartHandler);
        cell.removeEventListener('mouseover', cell._dragOverHandler);
        
        const dragStartHandler = (e) => {
             if (!e.ctrlKey && !e.shiftKey) {
          }
            cell.focus();
            
            if (e.ctrlKey) {
                if (selectedCells.includes(cell)) {
                    cell.classList.remove('range-selected');
                    selectedCells = selectedCells.filter(c => c !== cell);
                } else {
                    addToSelection(cell);
                }
                e.preventDefault();
                return;
            }
            if (e.shiftKey && activeCell) {
                selectRange(activeCell, cell);
                e.preventDefault();
                return;
            }
            isDragging = true;
            dragStartCell = cell;
            lastDragCell = cell;
            clearSelection();
            addToSelection(cell);
        };
        
        const dragOverHandler = () => {
            if (!isDragging) return;
            if (cell === lastDragCell) return;
            lastDragCell = cell;
            selectRange(dragStartCell, cell);
        };
        
        cell.addEventListener('mousedown', dragStartHandler);
        cell.addEventListener('mouseover', dragOverHandler);
        
        cell._dragStartHandler = dragStartHandler;
        cell._dragOverHandler = dragOverHandler;
    });
    
    document.addEventListener('mouseup', () => {
        isDragging = false;
        dragStartCell = null;
        lastDragCell = null;
    });
    
    document.querySelectorAll('.editable-cell').forEach(cell => {
        cell.onfocus = null;
        cell.onblur = null;
        
        cell.addEventListener('focus', () => setActiveCell(cell));
        cell.addEventListener('blur', () => {
    captureState();
    if (activeCell === cell) {
        const currentValue = cell.innerText.trim();
        const storedFormula = cellFormulas.get(cell);
        if (!currentValue.startsWith('=') && storedFormula) {
            cellFormulas.delete(cell);
        }
        updateValueDisplayForCell(cell);
        
        // --- Re‑validate error on edit ---
        if (cell.classList.contains('validation-error')) {
            const errorMsg = cell.getAttribute('data-error') || '';
            const num = parseFloat(currentValue);
            let isValid = false;
            // Parse the error message to extract the rule
            if (errorMsg.includes('between') || errorMsg.includes('must be between')) {
                const match = errorMsg.match(/(\d+)\s*[-–]\s*(\d+)/) || errorMsg.match(/(\d+) and (\d+)/);
                if (match && !isNaN(num)) {
                    const min = parseFloat(match[1]);
                    const max = parseFloat(match[2]);
                    isValid = num >= min && num <= max;
                }
            } else if (errorMsg.includes('cannot exceed') || errorMsg.includes('≤')) {
                const match = errorMsg.match(/(\d+)/);
                if (match && !isNaN(num)) {
                    const max = parseFloat(match[1]);
                    isValid = num <= max;
                }
            } else if (errorMsg.includes('not be empty')) {
                isValid = currentValue !== '';
            }
            
            if (isValid) {
                cell.classList.remove('validation-error');
                const btn = cell.querySelector('.error-explain-btn');
                if (btn) btn.remove();
                cell.removeAttribute('data-error');
                cell.removeAttribute('data-error-id');
            } else if (!isValid && num !== undefined && !isNaN(num)) {
                // Keep the error – no change
            }
        }
    }
});
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

function insertAtCursor(input, text) {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const value = input.value;
    input.value = value.slice(0, start) + text + value.slice(end);
    input.selectionStart = input.selectionEnd = start + text.length;
    input.focus();
}

const formulaInput = document.getElementById('formulaInput');
if (formulaInput) {
    document.addEventListener('click', (e) => {
        if (e.target.classList && e.target.classList.contains('editable-cell') && document.activeElement === formulaInput) {
            e.preventDefault();
            const row = e.target.parentElement.rowIndex;
            const col = e.target.cellIndex - 1;
            const ref = numToCol(col) + row;
            insertAtCursor(formulaInput, ref);
        }
    });
}

// Function Buttons (SUM, MIN, etc)
document.querySelectorAll('.func-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!activeCell) return;
        const func = btn.getAttribute('data-func');
        const smartRange = getSmartRange(activeCell);
        const fInput = document.getElementById('formulaInput');
        if (fInput) {
            if (smartRange) {
                fInput.value = `=${func.toUpperCase()}(${smartRange})`;
            } else {
                fInput.value = `=${func.toUpperCase()}(`;
            }
            if (typeof window.showFormulaHint === 'function') {
                window.showFormulaHint(fInput.value);
            }
            updateCellFromFormulaBar();
            activeCell.focus();
        }
    });
});

// ==========================================
// 5. FORMATTING TOOLBAR & COLORS (updated for multi-cell)
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
    
    if (selectedCells.length > 0) {
        applyFormatToSelection(property, value);
    } else {
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
                if (activeCell) activeCell.style[styleProperty] = trueOriginal;
            });
            item.addEventListener('click', function(e) {
                e.stopPropagation();
                if (!activeCell) return;
                let val = this.getAttribute('data-val');
                if (styleProperty === 'fontSize' && !val.includes('px')) val += 'px';
                trueOriginal = val;
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
                applyFormat('fontWeight', isBold ? 'normal' : 'bold');
                this.classList.toggle('active-format', !isBold);
            } else if (cmd === 'italic') {
                const isItalic = activeCell.style.fontStyle === 'italic';
                applyFormat('fontStyle', isItalic ? 'normal' : 'italic');
                this.classList.toggle('active-format', !isItalic);
            } else if (cmd === 'underline') {
                const currentDeco = activeCell.style.textDecoration;
                if (currentDeco.includes('underline double')) {
                    applyFormat('textDecoration', 'none');
                    this.classList.remove('active-format');
                    this.style.borderBottom = "none";
                } else if (currentDeco.includes('underline')) {
                    applyFormat('textDecoration', 'underline double');
                    this.classList.add('active-format');
                    this.style.borderBottom = "3px double #1e6f3f";
                } else {
                    applyFormat('textDecoration', 'underline');
                    this.classList.add('active-format');
                    this.style.borderBottom = "3px solid #1e6f3f";
                }
            }
        });
    });

    const excelColors = [
        '#ffffff', '#000000', '#eeece1', '#1f497d', '#4f81bd', '#c0504d',
        '#f2f2f2', '#808080', '#ddd9c3', '#c6d9f1', '#dbe5f1', '#f2dcdb',
        '#d9d9d9', '#595959', '#c4bd97', '#8db4e2', '#b8cce4', '#e6b8b7',
        '#bfbfbf', '#404040', '#938953', '#548dd4', '#95b3d7', '#d99694',
        '#ff0000', '#00ff00', '#0000ff', '#ffff00', '#00ffff', '#ff00ff'
    ];

    window.applyColor = (color, isText) => {
        if (!activeCell) return;
        if (selectedCells.length > 0) {
            for (let cell of selectedCells) {
                cell.style[isText ? 'color' : 'backgroundColor'] = color;
            }
            captureState();
        } else {
            activeCell.style[isText ? 'color' : 'backgroundColor'] = color;
            captureState();
        }
        const ind = document.querySelector(`#${isText ? 'textColorDropdown' : 'fillColorDropdown'} .color-indicator`);
        if (ind) ind.style.backgroundColor = color;
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
            swatch.className = 'color-swatch';
            swatch.style.backgroundColor = color;
            swatch.addEventListener('mouseenter', () => {
                if (activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = color;
            });
            swatch.addEventListener('mouseleave', () => {
                if (activeCell) activeCell.style[isText ? 'color' : 'backgroundColor'] = trueOriginalColor;
            });
            swatch.addEventListener('click', (e) => {
                e.stopPropagation();
                if (activeCell) {
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
// 6. ROW/COLUMN OPERATIONS (unchanged)
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
            // Include template-only columns if they have actual data (not just '-' placeholders)
            const colHasData = Array.from(document.querySelectorAll('#tableBody tr')).some(tr => {
                const cell = tr.querySelectorAll('td.editable-cell')[idx];
                const val = cell ? cell.innerText.trim() : '';
                return val !== '' && val !== '-';
            });
            if (!isTemp || mapped || colHasData) {
                colIndices.push(idx);
                headers.push(text);
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
    const formulaInput = document.getElementById('formulaInput');
if (formulaInput) {
    formulaInput.addEventListener('input', (e) => window.showFormulaHint(e.target.value));
}

    const formulaDropdown = document.getElementById('formulaDropdown');
if (formulaDropdown) {
    formulaDropdown.addEventListener('change', function() {
        const selected = this.value;
        if (selected && activeCell) {
            const smartRange = getSmartRange(activeCell);
            const fInput = document.getElementById('formulaInput');
            if (smartRange) {
                fInput.value = `=${selected}(${smartRange})`;
            } else {
                fInput.value = `=${selected}(`;
            }
            showFormulaHint(fInput.value);
            fInput.focus();
            updateCellFromFormulaBar();
            this.selectedIndex = 0;
        }
    });
}
// Floating formula panel
const formulaBtn = document.getElementById('formulaPopupBtn');
const formulaPanel = document.getElementById('formulaPanel');

if (formulaBtn && formulaPanel) {
    formulaBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const rect = formulaBtn.getBoundingClientRect();
        let top = rect.bottom + window.scrollY + 5;
        let left = rect.left + window.scrollX;
        const panelWidth = formulaPanel.offsetWidth;
        const panelHeight = formulaPanel.offsetHeight;
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        if (left + panelWidth > viewportWidth + window.scrollX) {
            left = viewportWidth + window.scrollX - panelWidth - 10;
        }
        if (left < window.scrollX) {
            left = window.scrollX + 10;
        }
        if (top + panelHeight > window.scrollY + viewportHeight) {
            top = rect.top + window.scrollY - panelHeight - 5;
        }
        formulaPanel.style.top = top + 'px';
        formulaPanel.style.left = left + 'px';
        formulaPanel.style.display = 'block';
    });

    document.addEventListener('click', (e) => {
        if (!formulaPanel.contains(e.target) && e.target !== formulaBtn) {
            formulaPanel.style.display = 'none';
        }
    });

    document.querySelectorAll('.panel-formula-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!activeCell) return;
        const func = btn.getAttribute('data-func');
        const smartRange = getSmartRange(activeCell);
        const fInput = document.getElementById('formulaInput');
        if (fInput) {
            if (smartRange) {
                fInput.value = `=${func.toUpperCase()}(${smartRange})`;
            } else {
                fInput.value = `=${func.toUpperCase()}(`;
            }
            if (typeof window.showFormulaHint === 'function') {
                window.showFormulaHint(fInput.value);
            }
            updateCellFromFormulaBar();
            activeCell.focus();
        }
        formulaPanel.style.display = 'none';
    });
});
}

    // --- Validation error highlighting (deduplicated) ---
if (window.DJANGO_VARS.errorsData && window.DJANGO_VARS.errorsData.length) {
    // Use a Map to store only one button per cell
    const cellToError = new Map();
    window.DJANGO_VARS.errorsData.forEach(err => {
        const row = err.row - 1;
        const errCol = err.column.trim().toLowerCase();
        const headers = Array.from(document.querySelectorAll('#headerRow th:not(.row-header-cell)'));
        const normalize = s => s.replace(/[\s_()%\-/]/g, '').toLowerCase();
        const colIndex = headers.findIndex(th => {
            const label = th.querySelector('.header-label');
            if (!label) return false;
            const headerText = label.innerText.trim().toLowerCase();
            return normalize(headerText) === normalize(errCol);
        });
        if (colIndex >= 0) {
            const cell = document.querySelector(`#tableBody tr:nth-child(${row+1}) td.editable-cell:nth-child(${colIndex+2})`);
            if (cell && !cellToError.has(cell)) {
                cellToError.set(cell, err);
                cell.classList.add('validation-error');
                cell.setAttribute('data-error', err.message);
                cell.setAttribute('data-error-id', err.id);
                const explainBtn = document.createElement('button');
                explainBtn.textContent = 'Explain';
                explainBtn.className = 'error-explain-btn';
                explainBtn.style.display = 'none';
                explainBtn.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    fetch('/ai-explain/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.DJANGO_VARS.csrfToken },
                        body: JSON.stringify({ result_id: err.id })
                    })
                    .then(res => res.json())
                    .then(data => {
                        const panel = document.createElement('div');
                        panel.className = 'floating-explanation-panel';
                        panel.innerHTML = `
                            <div class="ai-explanation-box">
                                <div class="ai-insight-header">
                                    <span class="sparkle-icon">✨</span>
                                    <strong>Intelligent Auditor Analysis</strong>
                                </div>
                                <div class="ai-content">${markdownToHtml(data.explanation)}</div>
                            </div>
                            <button class="close-explanation">×</button>
                        `;
                        document.body.appendChild(panel);
                        panel.querySelector('.close-explanation').onclick = () => panel.remove();
                        setTimeout(() => panel.remove(), 10000);
                    })
                    .catch(err => console.error(err));
                };
                cell.appendChild(explainBtn);
                cell.addEventListener('mouseenter', () => explainBtn.style.display = 'inline-block');
                cell.addEventListener('mouseleave', () => explainBtn.style.display = 'none');
            }
        }
    });
}

    // --- Recommendations panel (always visible, placed after status bar) ---
const panel = document.createElement('div');
panel.id = 'recommendationsPanel';
panel.className = 'recommendations-wrapper';
panel.innerHTML = `
    <h3 class="section-title"><span class="icon-sm">💡</span> Intelligent Recommendations</h3>
    <div class="recommendation-grid" id="recGrid"></div>
`;
const statusBar = document.querySelector('.status-bar');
if (statusBar) {
    statusBar.insertAdjacentElement('afterend', panel);
} else {
    document.body.appendChild(panel);
}
const recGrid = document.getElementById('recGrid');
if (window.DJANGO_VARS.recommendations && window.DJANGO_VARS.recommendations.length) {
    window.DJANGO_VARS.recommendations.forEach(rec => {
        const card = document.createElement('div');
        card.className = 'rec-card';
        card.innerHTML = `
            <div class="rec-header"><h4>Missing Column: <span>${rec.column}</span></h4></div>
            <div class="rec-body">
                <p>${rec.message}</p>
                <div class="formula-box"><strong>Formula:</strong> <code>${rec.formula}</code></div>
            </div>
        `;
        recGrid.appendChild(card);
    });
} else {
    const noRecCard = document.createElement('div');
    noRecCard.className = 'rec-card';
    noRecCard.innerHTML = `
        <div class="rec-body"><p><strong>✓ Structure Verified:</strong> All expected columns and formulas are present.</p></div>
    `;
    recGrid.appendChild(noRecCard);
}

    captureState();
    console.log("🔄 Editor initialized with multi‑cell selection and advanced formulas.");
    console.log("🔄 STEP 5 (JS IN): Page loaded. What did Django give us?");
    console.log("Raw DJANGO_VARS.styleData type:", typeof window.DJANGO_VARS.styleData);
    console.log("Raw DJANGO_VARS.styleData value:", window.DJANGO_VARS.styleData);
    console.log("Parsed styles variable:", styles);
}

init();

