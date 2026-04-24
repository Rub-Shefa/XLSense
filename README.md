# XLSense

Intelligent Data Workflow and Spreadsheet Automation Platform. Upload `.xlsx`, `.csv`, `.pdf`, or `.txt` files, select a domain (Academic, HR, Finance, Inventory), and get back structured, validated spreadsheets with auto-applied formulas, error detection, and AI-powered explanations.

## What It Does

- **Smart File Upload** — Upload `.xlsx`, `.csv`, `.pdf`, and `.txt` files with pre-upload validation (type, size). AI converts unstructured PDF/text to structured Excel.
- **Domain Selection** — Choose from Academic, HR, Finance, or Inventory domains to apply the right templates, rules, and formulas
- **Automatic Validation** — Domain-specific rules detect logical errors, missing values, and data inconsistencies
- **Formula Auditing** — Verifies existing formulas and recommends new ones based on your data
- **Data Quality Scoring** — Assigns a quality score to each uploaded file based on validation results
- **AI Explanations** — Generates plain-language explanations for formulas and corrections via OpenAI-compatible API
- **AI Column Matching** — Uses AI to automatically map file columns to domain template columns on first editor load
- **Live Cell Validation** — Real-time per-cell validation as you type in the workbook editor
- **Workbook Editor** — Edit spreadsheets with smart column mapping, fuzzy column detection, and style preservation
- **Text Import** — Convert raw PDF/text files to structured Excel using AI (with fallback parsing)
- **Structured Excel Output** — Produces clean, formatted `.xlsx` files with results and explanations
- **Theme Toggle** — Light, medium, and dark mode themes
- **Audit Trail** — Logs all user actions for compliance and history tracking, with search and filter
- **Soft Delete / Trash** — Files move to trash with 30-day expiry before permanent deletion
- **Role-Based Access** — Admin and User roles with separate dashboards and permissions

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 6.0.2 (Python) |
| Database | MySQL (via XAMPP) |
| Data Processing | pandas 2.3.3, openpyxl 3.1.5 |
| PDF Processing | PyPDF2 3.0.1 |
| AI Integration | OpenAI-compatible API (any OpenAI-compatible provider) |
| Frontend | HTML, CSS, JavaScript (Django templates) |
| Testing | pytest 9.0.2, pytest-django, pytest-cov, Playwright |
| Linting | ruff |

## Project Structure

```
XLSense/
├── automation/          # Main Django app
│   ├── models.py      # DomainTemplate, ValidationRule, FormulaRule, UploadedFile, ValidationResult, AuditLog
│   ├── views.py      # Homepage, login, register, dashboard, upload, history, report, AI explain, preview, download
│   ├── editor_views.py  # Workbook editor, save, cell validation
│   ├── text_import_views.py  # PDF/text to CSV conversion via AI
│   ├── utils.py      # Validation, formula audit, AI explanation, column matching, quality scoring
│   ├── forms.py      # CustomUserCreationForm
│   ├── forms_text_import.py  # TextFileUploadForm
│   ├── selectors.py  # Rule fetching per domain
│   ├── urls.py      # URL routing
│   └── admin.py    # Django admin configuration
├── XLSense/             # Django project settings and config
│   └── settings.py   # Database, middleware, static files
├── templates/           # 15 HTML templates (base, homepage, login, register, upload, dashboard, report, editor, etc.)
├── tests/               # 10 pytest test files (views, utils, models, forms, selectors, edge cases, workflows, editor, frontend)
├── test_files/          # Sample files: 18 per domain (valid, invalid, boundary xlsx/csv/pdf/txt)
├── docs/                # PRD, ERD (DBML/Mermaid/PlantUML), NFRs, requirements, user journeys
├── database/            # SQL schema dump (xlsense_db.sql)
├── static/              # CSS (theme.css, editor_styles.css), JS (editor_logic.js), SVG, images
├── uploads/             # Uploaded files directory
├── manage.py            # Django management CLI
├── requirements.txt    # Python dependencies
└── .env.example        # Environment variable template
```

## Prerequisites

- **Python 3.13+**
- **MySQL** (XAMPP recommended for local development)
- **pip** (Python package manager)

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd XLSense
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up the database

Start MySQL via XAMPP, then create the database:

```sql
CREATE DATABASE xlsense_db;
```

Import the schema:

```bash
mysql -u root xlsense_db < database/xlsense_db.sql
```

### 5. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DATABASE_PASSWORD=""                          # Leave empty for XAMPP default
AI_API_URL="https://api.openai.com/v1/chat/completions"
AI_API_KEY="your-api-key"
AI_MODEL="gpt-4o"
```

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create superuser (optional)

```bash
python manage.py createsuperuser
```

### 8. Start the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

## URL Routes

| Path | Description |
|------|-------------|
| `/` | Homepage / Login redirect |
| `/login/` | User login |
| `/register/` | User registration |
| `/logout/` | User logout |
| `/dashboard/` | User dashboard |
| `/admin/` | Admin dashboard |
| `/system-stats/` | System statistics |
| `/audit-logs/` | Paginated audit logs with search/filter |
| `/upload/` | File upload with domain selection |
| `/history/` | Upload history |
| `/trash/` | Soft-deleted files (30-day expiry) |
| `/report/<file_id>/` | Validation report |
| `/manage-templates/` | Domain template management |
| `/ai-explain/` | AI formula explanations (POST, CSRF exempt) |
| `/editor/` | Workbook editor list |
| `/editor/<file_id>/` | Workbook editor |
| `/editor/<file_id>/save/` | Save workbook changes |
| `/validate-cell/` | Live single-cell validation |
| `/text-import/` | PDF/text to Excel conversion |
| `/text-import/download/` | Download AI-converted Excel |
| `/preview/<file_id>/` | Excel table preview (JSON) |
| `/download/<file_id>/` | Download formatted Excel |
| `/api/files/<file_id>/status/` | Soft delete / restore |

## Testing

### Run all tests
```bash
pytest
```

### Run by file
```bash
pytest tests/test_views.py
pytest tests/test_utils.py
pytest tests/test_models.py
pytest tests/test_forms.py
pytest tests/test_selectors.py
pytest tests/test_edge_cases.py
pytest tests/test_workflows.py
pytest tests/test_editor_views.py
pytest tests/test_frontend.py
```

### Run by class
```bash
pytest tests/test_views.py::TestAiExplainView
```

### Run by method
```bash
pytest tests/test_views.py::TestAiExplainView::test_ai_explain_returns_json
```

### With coverage
```bash
pytest --cov=automation --cov-report=term-missing
```

### Linting
```bash
ruff check .
```

### Formatting
```bash
ruff format .
```

Sample test data is provided in `test_files/` — 18 files each for academic, hr, finance, and inventory domains (valid, invalid, and boundary cases in xlsx, csv, pdf, and txt formats).

## Domain Templates

Each domain has predefined validation rules and formula rules:

| Domain | Example Rules | Example Formulas |
|--------|--------------|-----------------|
| Academic | Grade range checks, attendance validation | GPA calculation, weighted averages |
| HR | Salary bounds, date validation | Payroll calculations, tax deductions |
| Finance | Budget limits, category checks | Variance analysis, tax formulas |
| Inventory | Stock level checks, price validation | Total value, reorder calculations |

## API Configuration

XLSense supports any OpenAI-compatible API for AI explanations and text-to-spreadsheet conversion. Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` in your `.env` file. If no API key is configured, the system falls back to basic text explanations and rule-based parsing.