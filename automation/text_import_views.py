from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import csv
import io
import json
import PyPDF2
import openpyxl
import requests
from django.shortcuts import render
from django.http import HttpResponse
from django.conf import settings
from .forms_text_import import TextFileUploadForm

# Load AI settings from .env
AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL", "https://openrouter.ai/api/v1/chat/completions")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-3.5-turbo")

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF file."""
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def call_ai_to_csv(raw_text):
    """
    Send raw text to AI and ask for CSV output with headers.
    Returns CSV string or None if fails.
    """
    if not AI_API_KEY:
        raise Exception("AI_API_KEY not set in environment")

    prompt = f"""You are a data extraction assistant. Convert the following text into a structured CSV table.
- Detect column headers automatically.
- Ensure each row has the same number of columns.
- Output ONLY valid CSV data, no extra text, no markdown.
- Use double quotes for fields that contain commas or newlines.

Text:
{raw_text[:3000]}  # limit to avoid token overflow
"""

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    response = requests.post(AI_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    csv_content = data["choices"][0]["message"]["content"].strip()

    # Remove markdown code fences if present
    if csv_content.startswith("```"):
        lines = csv_content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        csv_content = "\n".join(lines)

    return csv_content

def parse_csv_to_rows(csv_string):
    """Convert CSV string to list of lists."""
    reader = csv.reader(io.StringIO(csv_string))
    return [row for row in reader]

def fallback_parse_text_to_rows(raw_text):
    """
    Rule-based fallback when AI fails.
    Splits lines by whitespace to create rows.
    Works for space/tab-separated values.
    Returns list of lists (rows).
    """
    rows = []
    for line in raw_text.strip().splitlines():
        if line.strip():
            # Split on any whitespace (space, tab)
            cols = line.split()
            if cols:
                rows.append(cols)
    
    # If only one row, assume it's a single column
    if len(rows) == 1:
        rows = [[cell] for cell in rows[0]]
    
    return rows if rows else None

def text_import_view(request):
    preview_rows = None
    original_filename = None
    error = None

    if request.method == "POST":
        form = TextFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES["file"]
            original_filename = uploaded_file.name
            raw_text = ""

            # Extract text based on file type
            if uploaded_file.name.lower().endswith(".txt"):
                raw_text = uploaded_file.read().decode("utf-8", errors="ignore")
            elif uploaded_file.name.lower().endswith(".pdf"):
                raw_text = extract_text_from_pdf(uploaded_file)
            else:
                error = "Unsupported file type. Please upload .txt or .pdf."

            if raw_text and not error:
                csv_data = None
                used_fallback = False
                try:
                    csv_data = call_ai_to_csv(raw_text)
                    preview_rows = parse_csv_to_rows(csv_data)
                    if not preview_rows:
                        raise ValueError("AI returned empty table")
                except Exception as e:
                    # AI failed – use fallback
                    print(f"AI failed: {e}, using fallback parser")
                    preview_rows = fallback_parse_text_to_rows(raw_text)
                    used_fallback = True
                    if not preview_rows:
                        error = f"AI failed and fallback could not parse text: {str(e)}"
                    else:
                        request.session["ai_fallback_used"] = True
    
                if preview_rows and not error:
                    request.session["ai_export_rows"] = preview_rows
                    request.session["ai_export_filename"] = original_filename.rsplit(".", 1)[0]
                    if used_fallback:
                        from django.contrib import messages
                        messages.warning(request, "AI service unavailable. Used basic text parser. Table may be less accurate.")
    else:
        form = TextFileUploadForm()

    return render(request, "text_import.html", {
        "form": form,
        "preview_rows": preview_rows,
        "original_filename": original_filename,
        "error": error,
    })

def download_ai_excel(request):
    rows = request.session.get("ai_export_rows")
    if not rows:
        return HttpResponse("No data to export", status=400)

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)

    filename = request.session.get("ai_export_filename", "ai_export") + ".xlsx"
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response