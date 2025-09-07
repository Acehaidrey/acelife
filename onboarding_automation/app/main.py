
import os
import argparse
import requests
import json
from pdfrw import PdfReader, PdfWriter, IndirectPdfDict

# --- SCRIPT CONFIGURATION ---
# The directory where your template PDF files are stored.
TEMPLATE_DIR = "../templates"
# The directory where the script will save the newly filled PDFs.
OUTPUT_DIR = "../output"

# --- DOCUSEAL API CONFIGURATION ---
# These should be set as environment variables for security, but are here for clarity.
# You will get this URL from your Railway deployment.
DOCUSEAL_URL = os.environ.get("DOCUSEAL_URL", "https://your-docuseal-instance.up.railway.app")
# You will generate this API key from within the DocuSeal settings.
API_KEY = os.environ.get("DOCUSEAL_API_KEY", "YOUR_DOCUSEAL_API_KEY")


def fill_pdf_template(template_path, output_path, employee_name):
    """
    Fills a PDF form field with the employee's name.

    This function assumes your PDF has a fillable form field with the
    exact name 'employee_name'.
    """
    try:
        template_pdf = PdfReader(template_path)
        
        # This is the key part: find and fill the form fields.
        for page in template_pdf.pages:
            annotations = page.get("/Annots")
            if annotations:
                for annotation in annotations:
                    if annotation.get("/Subtype") == "/Widget" and annotation.get("/T"):
                        field_name = annotation.get("/T")[1:-1] # Field name, e.g., (employee_name)
                        if field_name == 'employee_name':
                            annotation.update(
                                IndirectPdfDict(V=f'{employee_name}')
                            )
        
        # Flatten the form fields to make them non-editable
        for page in template_pdf.pages:
            if page.get("/Annots"):
                page.Annots = []

        writer = PdfWriter()
        writer.addpages(template_pdf.pages)
        writer.write(output_path)
        
        print(f"Successfully filled: {output_path}")
        return True
    except Exception as e:
        print(f"Error filling PDF {template_path}: {e}")
        return False

def send_for_signature(pdf_path, signer_email, owner_email):
    """
    Uploads a PDF to DocuSeal and sends it for signature.
    """
    try:
        with open(pdf_path, "rb") as pdf_file:
            files = {'file': (os.path.basename(pdf_path), pdf_file, 'application/pdf')}
            payload = {
                "submitters": [{"email": signer_email, "role": "Employee"}],
                "send_email": True,
                "emails": {"completed": [owner_email]}
            }
            data = {'data': json.dumps(payload)}
            headers = {"X-Auth-Token": API_KEY}

            print(f"Uploading {os.path.basename(pdf_path)} to DocuSeal...")
            response = requests.post(
                f"{DOCUSEAL_URL}/api/submissions",
                headers=headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            print(f"Successfully sent {os.path.basename(pdf_path)} to {signer_email}.")
            return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error for {os.path.basename(pdf_path)}: {e.response.text}")
        return None
    except FileNotFoundError:
        print(f"File not found: {pdf_path}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Onboard a new employee by filling and sending documents for signature.")
    parser.add_argument("--name", required=True, help="The full name of the employee.")
    parser.add_argument("--email", required=True, help="The email address of the employee.")
    parser.add_argument("--owner-email", required=True, help="Your email for notifications.")
    args = parser.parse_args()

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    template_files = [f for f in os.listdir(TEMPLATE_DIR) if f.endswith('.pdf')]
    if not template_files:
        print(f"No PDF templates found in '{TEMPLATE_DIR}'. Please add your templates.")
        return

    print(f"Starting onboarding for {args.name} ({args.email})...")

    for template_name in template_files:
        template_path = os.path.join(TEMPLATE_DIR, template_name)
        output_filename = f"{args.name.replace(' ', '_')}_{template_name}"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        # Step 1: Fill the PDF
        if fill_pdf_template(template_path, output_path, args.name):
            # Step 2: Send the filled PDF for signature
            send_for_signature(output_path, args.email, args.owner_email)

    print("\nOnboarding process complete. Documents have been sent for signature via DocuSeal.")


if __name__ == "__main__":
    main()
