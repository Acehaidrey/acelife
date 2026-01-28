
import requests
import json

# --- Configuration ---
# URL of your self-hosted DocuSeal instance from Railway
DOCUSEAL_URL = "https://your-docuseal-instance.up.railway.app" 
# API key generated from DocuSeal Settings -> API Keys
API_KEY = "YOUR_DOCUSEAL_API_KEY" 

# Path to the PDF you have already filled and saved
PDF_PATH = "/path/to/your/filled_document.pdf" 
# Email of the person who needs to sign
SIGNER_EMAIL = "new.employee@example.com" 
# Your email, to be notified when it's complete
YOUR_EMAIL = "your.email@yourcompany.com"

# --- Main Logic ---

# 1. Create the submission (the document to be signed)
try:
    with open(PDF_PATH, "rb") as pdf_file:
        # The 'files' part of the request is for multipart/form-data upload
        files = {'file': (PDF_PATH.split('/')[-1], pdf_file, 'application/pdf')}
        
        # The 'data' part contains the JSON payload for the signers
        payload = {
            "submitters": [
                {
                    "email": SIGNER_EMAIL,
                    "role": "Signer 1" 
                }
            ],
            "send_email": True, # Tell DocuSeal to email the signers
            "emails": {
                "completed": [YOUR_EMAIL] # Email you when done
            }
        }
        
        # Need to send the payload as a string in the 'data' field
        data = {'data': json.dumps(payload)}

        headers = {
            "X-Auth-Token": API_KEY
        }

        print("Uploading document to DocuSeal for signature...")
        
        response = requests.post(
            f"{DOCUSEAL_URL}/api/submissions",
            headers=headers,
            files=files,
            data=data
        )

        # Raise an exception if the request failed
        response.raise_for_status() 

        result = response.json()
        print(f"Successfully created submission! ID: {result['id']}")
        print(f"An email has been sent to {SIGNER_EMAIL} for signing.")

except requests.exceptions.RequestException as e:
    print(f"An API error occurred: {e}")
    if e.response:
        print(f"Error details: {e.response.text}")
except FileNotFoundError:
    print(f"Error: The file was not found at {PDF_PATH}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

