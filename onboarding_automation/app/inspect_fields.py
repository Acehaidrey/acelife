import sys
from pdfrw import PdfReader

def inspect_pdf_fields(file_path):
    """Prints all fillable form field names from a PDF."""
    print(f"Inspecting fields for: {file_path}\n---")
    try:
        template_pdf = PdfReader(file_path)
        fields = []
        for page in template_pdf.pages:
            annotations = page.get("/Annots")
            if annotations:
                for annotation in annotations:
                    if annotation.get("/Subtype") == "/Widget" and annotation.get("/T"):
                        field_name = annotation.get("/T")[1:-1]
                        fields.append(field_name)
        
        if fields:
            print("Found the following form fields:")
            for field in sorted(fields):
                print(f"  - {field}")
        else:
            print("No fillable form fields found in this PDF.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        inspect_pdf_fields(sys.argv[1])
    else:
        print("Usage: python inspect_fields.py <path_to_pdf_file>")
