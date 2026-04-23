# XLSense

Intelligent Data Workflow and Spreadsheet Automation Platform. Upload `.xlsx` or `.csv` files, select a domain (Academic, HR, Finance, Inventory), and get back structured, validated spreadsheets with auto-applied formulas, error detection, and AI-powered explanations.

## What It Does

- **Smart File Upload** — Upload `.xlsx` and `.csv` files with pre-upload validation (type, size)
- **Domain Selection** — Choose from Academic, HR, Finance, or Inventory domains to apply the right templates, rules, and formulas
- **Automatic Validation** — Domain-specific rules detect logical errors, missing values, and data inconsistencies
- **Formula Auditing** — Verifies existing formulas and recommends new ones based on your data
- **Data Quality Scoring** — Assigns a quality score to each uploaded file based on validation results
- **AI Explanations** — Generates plain-language explanations for formulas and corrections via OpenAI-compatible API
- **Workbook Editor** — Edit spreadsheets with smart column mapping, fuzzy column detection, and style preservation
- **Structured Excel Output** — Produces clean, formatted `.xlsx` files with results and explanations
- **Theme Toggle** — Light and dark mode themes
- **Audit Trail** — Logs all user actions for compliance and history tracking
- **Role-Based Access** — Admin and User roles with separate dashboards and permissions

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 6.0 (Python) |
| Database | MySQL (via XAMPP) |
| Data Processing | pandas, openpyxl |
| AI Integration | OpenAI-compatible API |
| Frontend | HTML, CSS, JavaScript (Django templates) |
| Testing | pytest, pytest-django, pytest-cov, Playwright |
| Linting | ruff |

## Project Structure

```
XLSense/
├── automation/          # Main Django app (models, views, utils, forms, selectors, urls)
├── XLSense/             # Django project settings and config
├── templates/           # HTML templates (upload, dashboard, report, editor, etc.)
├── tests/               # pytest test suite (8 test files)
├── test_files/          # Sample CSV files for each domain (academic, hr, finance, inventory)
├── docs/                # PRD, ERD, requirements, NFRs
├── database/            # SQL schema dump
├── static/              # Static files (CSS, SVG icons)
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
|------|------------|
| `/` | Homepage |
| `/login/` | User login |
| `/register/` | User registration |
| `/logout/` | User logout |
| `/dashboard/` | User dashboard |
| `/admin/` | Admin dashboard |
| `/system-stats/` | System statistics |
| `/upload/` | File upload with domain selection |
| `/history/` | Upload history |
| `/report/<file_id>/` | Validation report |
| `/manage-templates/` | Domain template management |
| `/ai-explain/` | AI formula explanations |
| `/editor/` | Workbook editor list |
| `/editor/<file_id>/` | Workbook editor |
| `/preview/<file_id>/` | Excel table preview |
| `/download/<file_id>/` | Download formatted Excel |

## Testing

### Core testing
```bash
pytest                          # Run all tests
pytest tests/                   # Run all tests in tests/ directory
```

### Run specific test files
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

### Run specific test class
```bash
pytest tests/test_views.py::TestAiExplainView
```

### Run specific test method
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

Sample test data is provided in `test_files/` with valid, invalid, and boundary-case CSVs for each domain.

## Domain Templates

Each domain has predefined validation rules and formula rules:

| Domain | Example Rules | Example Formulas |
|--------|--------------|-----------------|
| Academic | Grade range checks, attendance validation | GPA calculation, weighted averages |
| HR | Salary bounds, date validation | Payroll calculations, tax deductions |
| Finance | Budget limits, category checks | Variance analysis, tax formulas |
| Inventory | Stock level checks, price validation | Total value, reorder calculations |

## API Configuration

XLSense supports any OpenAI-compatible API for AI explanations. Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` in your `.env` file. If no API key is configured, the system falls back to basic text explanations.

## Contributors

- **Rubaiya Akter** — Domain Selection, Formula Recommendation, Validation Engine
- **Adita Haq** — File Upload, Parsing, Data Detection, Output Generation
- **Farshid Abrar Labib** — Authentication, AI Suggestions, Rule Management, Logging, AI Integration