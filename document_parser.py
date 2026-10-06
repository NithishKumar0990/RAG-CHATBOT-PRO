# document_parser.py
import io
import csv
import pandas as pd
from pypdf import PdfReader
from docx import Document

def parse_tabular(uploaded_file) -> dict:
    """
    Parse uploaded tabular file (.csv, .xlsx) into a DataFrame and summary metadata.
    Returns: {"dataframe": df, "sheet_name": str, "row_count": int, "col_count": int, "columns": [col names]}
    """
    filename = getattr(uploaded_file, "filename", None) or getattr(uploaded_file, "name", "")
    if isinstance(uploaded_file, str):
        filename = uploaded_file
    filename = str(filename).lower()

    if hasattr(uploaded_file, "getvalue"):
        raw_bytes = uploaded_file.getvalue()
    elif hasattr(uploaded_file, "read"):
        raw_bytes = uploaded_file.read()
    elif isinstance(uploaded_file, bytes):
        raw_bytes = uploaded_file
    elif isinstance(uploaded_file, str):
        with open(uploaded_file, "rb") as f:
            raw_bytes = f.read()
    else:
        raise ValueError("Invalid file object provided to parse_tabular.")

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        raise ValueError("The file has no data")

    df = None
    sheet_name = "Sheet1"

    if filename.endswith(".csv"):
        bio = io.BytesIO(raw_bytes)
        try:
            df = pd.read_csv(bio, encoding="utf-8")
        except UnicodeDecodeError:
            bio.seek(0)
            try:
                df = pd.read_csv(bio, encoding="latin-1")
            except Exception as e:
                raise ValueError(f"Unable to read CSV file: {e}")
        except pd.errors.EmptyDataError:
            raise ValueError("The file has no data")
        except Exception as e:
            raise ValueError(f"Unable to read CSV file: {e}")
    elif filename.endswith(".xlsx"):
        bio = io.BytesIO(raw_bytes)
        try:
            excel_file = pd.ExcelFile(bio, engine="openpyxl")
            if not excel_file.sheet_names:
                raise ValueError("The file has no data")
            sheet_name = excel_file.sheet_names[0]
            df = excel_file.parse(sheet_name)
        except ValueError as ve:
            if "The file has no data" in str(ve):
                raise ve
            raise ValueError(f"Unable to read Excel file: {ve}")
        except Exception as e:
            raise ValueError(f"Unable to read Excel file: corrupted or invalid format ({e})")
    else:
        raise ValueError(f"Unsupported tabular file format: {filename}")

    if df is None or df.empty or len(df) == 0:
        raise ValueError("The file has no data")

    columns = [str(col) for col in df.columns]
    profile = compute_dataset_profile(df)

    return {
        "dataframe": df,
        "sheet_name": str(sheet_name),
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": columns,
        "profile": profile
    }

def compute_dataset_profile(df: pd.DataFrame) -> dict:
    """Compute local pandas vectorized profile (<200ms up to 100k rows)."""
    row_count = int(len(df))
    col_count = int(len(df.columns))
    if row_count == 0 or col_count == 0:
        return {
            "row_count": row_count,
            "col_count": col_count,
            "columns": [],
            "numeric_summary": {},
            "top_categories": {}
        }

    null_pct_series = (df.isna().mean() * 100.0).round(1)
    columns_info = []
    numeric_summary = {}
    top_categories = {}

    for col in df.columns:
        col_str = str(col)
        series = df[col]
        null_pct = float(null_pct_series.get(col, 0.0))

        if pd.api.types.is_numeric_dtype(series):
            dtype = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(series):
            dtype = "date"
        else:
            dtype = "text"

        non_null = series.dropna()
        samples = []
        if len(non_null) > 0:
            for v in non_null.iloc[:3].tolist():
                if hasattr(v, "item"):
                    v = v.item()
                if isinstance(v, (int, pd.Int64Dtype)):
                    samples.append(int(v))
                elif isinstance(v, float):
                    samples.append(round(float(v), 2))
                else:
                    samples.append(str(v))

        columns_info.append({
            "name": col_str,
            "dtype": dtype,
            "null_pct": null_pct,
            "sample_values": samples
        })

        if dtype == "numeric" and len(non_null) > 0:
            numeric_summary[col_str] = {
                "mean": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2)
            }
        elif dtype == "text":
            n_unique = int(series.nunique(dropna=True))
            if 0 < n_unique <= 20:
                top_5 = series.value_counts(dropna=True).head(5)
                top_categories[col_str] = {str(k): int(v) for k, v in top_5.items()}

    return {
        "row_count": row_count,
        "col_count": col_count,
        "columns": columns_info,
        "numeric_summary": numeric_summary,
        "top_categories": top_categories
    }

def parse_document(uploaded_file, return_pages: bool = False):
    """
    Parse uploaded file (PDF, DOCX, TXT, CSV) and return its text content.
    If return_pages=True, returns tuple (extracted_text, pages_list) where pages_list is
    a list of dicts [{'text': page_text, 'page': page_num}] for PDFs, or None for non-PDFs.
    """
    filename = uploaded_file.name.lower()
    
    try:
        if filename.endswith('.txt'):
            text = uploaded_file.getvalue().decode("utf-8", errors="replace")
            return (text, None) if return_pages else text
        
        elif filename.endswith('.pdf'):
            pdf_reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
            pages = []
            text = []
            for i, page in enumerate(pdf_reader.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    pages.append({"text": page_text, "page": i})
                    text.append(page_text)
            extracted = "\n".join(text)
            if len(extracted.strip()) < 100:
                raise ValueError("⚠️ This PDF has no extractable text (scanned/image-based). Please upload a text-based PDF or DOCX.")
            return (extracted, pages) if return_pages else extracted
        
        elif filename.endswith('.docx'):
            doc = Document(io.BytesIO(uploaded_file.getvalue()))
            text = [para.text for para in doc.paragraphs if para.text]
            extracted = "\n".join(text)
            return (extracted, None) if return_pages else extracted
            
        elif filename.endswith('.csv'):
            content = uploaded_file.getvalue().decode("utf-8", errors="replace").splitlines()
            reader = csv.reader(content)
            headers = next(reader, None)
            if not headers:
                return ("", None) if return_pages else ""
            
            text = []
            for row in reader:
                row_text = []
                for i, value in enumerate(row):
                    header = headers[i] if i < len(headers) else f"Column {i}"
                    row_text.append(f"{header}: {value}")
                text.append(" | ".join(row_text))
            extracted = "\n".join(text)
            return (extracted, None) if return_pages else extracted
            
        else:
            raise ValueError(f"Unsupported file format: {filename}")
            
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Error parsing file {filename}: {str(e)}")
