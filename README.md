<div align="center">

# XLSense

### Intelligent Data Workflow & Spreadsheet Automation Platform

A Django-based web application for **domain-aware spreadsheet validation, formula auditing, AI-assisted explanations, data-quality scoring, and interactive workbook editing**.

![XLSense](static/images/xlsense-hero.png)

</div>

---

## Overview

**XLSense** helps users turn raw spreadsheet and text-based data into cleaner, validated, and more understandable Excel workflows.

Users can upload spreadsheet files, select a business domain, run domain-specific validation rules, review formula recommendations, edit workbook data in the browser, and export a processed Excel file. XLSense also supports AI-assisted explanations and conversion of unstructured PDF/TXT content into structured spreadsheet data when an OpenAI-compatible API is configured.

The project was developed as a **Junior Design Project** at North South University.

---

## Key Features

- **Multi-format file input** — Supports `.xlsx`, `.csv`, `.pdf`, and `.txt` workflows.
- **Domain-specific validation** — Apply rules for Academic, HR, Finance, and Inventory data.
- **Formula auditing and recommendations** — Detect missing or incorrect computed values and recommend appropriate formulas.
- **Data-quality scoring** — Summarize validation quality using a numeric score.
- **AI-powered explanations** — Convert technical validation/formula issues into easier-to-understand explanations.
- **Text-to-spreadsheet conversion** — Extract PDF/TXT content and convert it into structured spreadsheet data with AI-assisted and fallback parsing.
- **Interactive workbook editor** — Edit spreadsheet values directly in the browser.
- **Smart column mapping** — Match uploaded columns with domain template columns using saved mappings, matching logic, and AI-assisted suggestions.
- **Live cell validation** — Re-check edited cells against domain rules without leaving the editor.
- **Spreadsheet functions** — Includes common functions such as `SUM`, `AVERAGE`, `COUNT`, `COUNTA`, `COUNTIF`, `MIN`, `MAX`, `IF`, `VLOOKUP`, and `XLOOKUP` support within the editor workflow.
- **Formatting support** — Preserve/edit spreadsheet presentation such as bold text, font color, background color, and other cell styling.
- **Upload history and file management** — View previously processed files and reopen them for editing.
- **Soft delete / trash workflow** — Deleted files can be restored during the configured retention period.
- **Audit logging** — Track important user actions such as uploads, downloads, edits, deletes, logins, and report access.
- **Role-based access** — Separate user and administrative functionality.
- **Theme support** — Light/dark interface styling.

---

## Application Workflow

```text
Upload File
    ↓
Choose Domain
    ↓
Parse & Preprocess Data
    ↓
Map Columns to Domain Rules
    ↓
Run Validation + Formula Checks
    ↓
Generate Quality Score & Recommendations
    ↓
Review AI Explanations
    ↓
Edit Workbook in Browser
    ↓
Revalidate Changes
    ↓
Save / Export Processed Excel File
```

For PDF/TXT input, XLSense first extracts the text and attempts to transform it into structured tabular data before continuing through the spreadsheet workflow.

---

## Supported Domains

| Domain | Typical Validation Examples | Typical Formula / Processing Examples |
|---|---|---|
| **Academic** | score ranges, grades, attendance, missing values | totals, weighted scores, GPA/grade calculations |
| **HR** | salary bounds, employee data, date/value checks | payroll, bonuses, deductions, calculated totals |
| **Finance** | budget limits, amount validation, category consistency | variance and total calculations |
| **Inventory** | quantity, stock, price, and reorder checks | inventory value and stock calculations |

Domain rules are stored in the database through `DomainTemplate`, `ValidationRule`, and `FormulaRule` models, so the validation layer is configurable rather than hard-coded to a single spreadsheet format.

---

## Technology Stack

| Area | Technology |
|---|---|
| Backend | **Python, Django 6.0.2** |
| Database | **MySQL** |
| Spreadsheet processing | **pandas, openpyxl** |
| PDF text extraction | **PyPDF2** |
| AI integration | **OpenAI-compatible REST API** |
| Frontend | **Django Templates, HTML, CSS, Vanilla JavaScript** |
| Testing | **pytest, pytest-django, pytest-cov** |
| End-to-end testing | **Playwright, pytest-playwright** |
| Code quality | **ruff** |

---

## Project Structure

```text
XLSense/
├── automation/                 # Main Django application
│   ├── migrations/             # Database migrations
│   ├── admin.py                # Django admin configuration
│   ├── editor_views.py         # Workbook editor + live validation views
│   ├── forms.py                # Application forms
│   ├── forms_text_import.py    # Text import forms
│   ├── models.py               # Core database models
│   ├── selectors.py            # Query/helper selectors
│   ├── text_import_views.py    # PDF/TXT → structured data workflow
│   ├── urls.py                 # Application routes
│   ├── utils.py                # Validation, AI, formula and helper logic
│   └── views.py                # Main application views
│
├── XLSense/                    # Django project configuration
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── static/
│   ├── css/                    # Theme and editor styling
│   ├── images/                 # Project images/assets
│   ├── js/                     # Workbook editor logic
│   └── svg/                    # Theme icons
│
├── templates/                  # Django HTML templates
├── test_files/                 # Domain-specific valid/invalid/boundary samples
├── tests/                      # Automated test suite
├── uploads/                    # Runtime uploaded/generated files
├── .env.example                # Environment-variable template
├── manage.py                   # Django command-line entry point
├── requirements.txt            # Python dependencies
└── README.md
```

---

## Prerequisites

Before running the project locally, install:

- **Python 3.13+**
- **MySQL** (XAMPP/MySQL can be used for local development)
- **pip**
- **Git**

An AI API key is **optional** for parts of the application that provide fallback behavior, but it is required for the full AI-assisted experience.

---

## Local Installation

### 1. Clone the repository

```bash
git clone https://github.com/RA-Shefaa/XLSense.git
cd XLSense
```

### 2. Create a virtual environment

#### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the MySQL database

Start MySQL and create a database named `xlsense_db`:

```sql
CREATE DATABASE xlsense_db;
```

The current Django configuration expects:

```text
Database: xlsense_db
Host:     127.0.0.1
Port:     3306
User:     root
```

### 5. Configure environment variables

Create a local `.env` file from `.env.example`.

#### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

#### macOS / Linux

```bash
cp .env.example .env
```

Example:

```env
DATABASE_PASSWORD=""
AI_API_URL="https://api.openai.com/v1/chat/completions"
AI_API_KEY="your-api-key"
AI_MODEL="your-model-id"
```

> Keep real API keys and credentials in `.env`. Do not commit `.env` to GitHub.

### 6. Apply database migrations

```bash
python manage.py migrate
```

### 7. Create an administrator account

```bash
python manage.py createsuperuser
```

### 8. Configure domain templates and rules

The application's validation behavior depends on database records for:

- `DomainTemplate`
- `ValidationRule`
- `FormulaRule`

Use the project's existing database data, Django admin, or the application's template-management interface to make sure the required Academic, HR, Finance, and Inventory rules are available.

### 9. Start the development server

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## Main Routes

| Route | Purpose |
|---|---|
| `/` | Homepage |
| `/login/` | Sign in |
| `/register/` | Create an account |
| `/dashboard/` | User dashboard |
| `/upload/` | Upload and process files |
| `/history/` | Upload history |
| `/trash/` | Restore soft-deleted files |
| `/report/<file_id>/` | Validation report |
| `/editor/` | Workbook list |
| `/editor/<file_id>/` | Interactive workbook editor |
| `/validate-cell/` | Live cell-validation endpoint |
| `/preview/<file_id>/` | Spreadsheet preview |
| `/download/<file_id>/` | Download processed Excel file |
| `/text-import/` | PDF/TXT structured import workflow |
| `/manage-templates/` | Domain/rule management |
| `/audit-logs/` | Audit-log view |
| `/admin/` | Django admin |

---

## AI Configuration

XLSense communicates with an **OpenAI-compatible chat-completions API** through environment variables:

```env
AI_API_URL="..."
AI_API_KEY="..."
AI_MODEL="..."
```

AI-assisted functionality is used for tasks such as:

- formula/validation explanations;
- column matching;
- converting unstructured text into tabular data.

Where implemented, fallback logic allows selected workflows to continue when AI is unavailable.

---

## Testing

The repository includes unit/integration-style tests, workflow tests, frontend checks, and domain-specific sample files.

### Run the complete test suite

```bash
pytest tests/
```

### Run with coverage

```bash
pytest tests/ --cov=automation --cov-report=term-missing
```

### Run a specific test module

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

### End-to-end testing

Install Playwright browsers once:

```bash
playwright install
```

Then run the relevant Playwright/pytest tests from the test suite.

---

## Code Quality

### Lint

```bash
ruff check .
```

### Format

```bash
ruff format .
```

---

## Data Model

The core application is organized around six main models:

- **DomainTemplate** — describes a domain-specific spreadsheet template.
- **ValidationRule** — stores validation conditions and error messages.
- **FormulaRule** — stores calculated-field/formula expectations.
- **UploadedFile** — tracks user files, processing state, mappings, styling, and trash state.
- **ValidationResult** — stores row/column-level validation failures.
- **AuditLog** — records important user actions.

This structure allows XLSense to keep validation logic configurable at the database level while connecting each result back to the user and uploaded workbook.

---

## Current Development Notes

This repository is currently configured primarily for **local/development use**. Before deploying publicly, move deployment-sensitive values such as Django's `SECRET_KEY`, `DEBUG`, allowed hosts, database credentials, and production security settings into environment-specific configuration.

Also review uploaded-file storage, production static-file handling, HTTPS, CSRF/cookie settings, API rate limits, and database permissions before using the application with real organizational data.

---

## Team

**Team Code XYZ — North South University**

- **Rubaiya Akter** — domain templates, validation/formula logic, workbook editor and spreadsheet functionality
- **Adita Haq** — uploads, parsing, preprocessing, output generation, PDF/TXT workflows and editor integration
- **Farshid Abrar Labib** — authentication, role-based interfaces, AI integration, audit logging, testing and project configuration

**Faculty Advisor:** Tanzilah Noor Shabnam, Senior Lecturer, Department of Electrical & Computer Engineering, North South University

---

## Contributing

For team development:

1. Pull the latest `main` branch.
2. Create a focused feature/fix branch.
3. Keep commits small and descriptive.
4. Run tests and linting before opening a pull request.
5. Do not commit `.env`, API keys, uploaded user files, virtual environments, or local editor settings unless they are intentionally shared project configuration.

Example:

```bash
git checkout -b fix/mapped-column-validation
# make changes
git add .
git commit -m "fix: resolve validation rules through saved column mappings"
git push -u origin fix/mapped-column-validation
```

---

## License

No explicit open-source license is currently included in this repository. If the team intends to distribute XLSense as an open-source project, add an appropriate `LICENSE` file and update this section.

---

<div align="center">

**XLSense — making spreadsheet validation more automated, domain-aware, and understandable.**

</div>
git