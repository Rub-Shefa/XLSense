from django import forms

class TextFileUploadForm(forms.Form):
    file = forms.FileField(
        label='Select a .txt or .pdf file',
        help_text='Only text files or PDFs (text-based)',
        widget=forms.FileInput(attrs={'accept': '.txt,.pdf'})
    )