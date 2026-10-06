# document_parser.py
import io
import csv
from pypdf import PdfReader
from docx import Document

def parse_document(uploaded_file) -> str:
    """
    Parse uploaded file (PDF, DOCX, TXT, CSV) and return its text content.
    """
    filename = uploaded_file.name.lower()
    
    try:
        if filename.endswith('.txt'):
            return uploaded_file.getvalue().decode("utf-8", errors="replace")
        
        elif filename.endswith('.pdf'):
            pdf_reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
            text = []
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            extracted = "\n".join(text)
            if len(extracted.strip()) < 100:
                raise ValueError("⚠️ This PDF has no extractable text (scanned/image-based). Please upload a text-based PDF or DOCX.")
            return extracted
        
        elif filename.endswith('.docx'):
            doc = Document(io.BytesIO(uploaded_file.getvalue()))
            text = [para.text for para in doc.paragraphs if para.text]
            return "\n".join(text)
            
        elif filename.endswith('.csv'):
            content = uploaded_file.getvalue().decode("utf-8", errors="replace").splitlines()
            reader = csv.reader(content)
            headers = next(reader, None)
            if not headers:
                return ""
            
            text = []
            for row in reader:
                row_text = []
                for i, value in enumerate(row):
                    header = headers[i] if i < len(headers) else f"Column {i}"
                    row_text.append(f"{header}: {value}")
                text.append(" | ".join(row_text))
            return "\n".join(text)
            
        else:
            raise ValueError(f"Unsupported file format: {filename}")
            
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Error parsing file {filename}: {str(e)}")
