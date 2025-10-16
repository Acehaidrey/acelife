
import os
import requests
from dotenv import load_dotenv

def verify_template():
    """Connects to DocuSeal and prints the fields for a given template."""
    
    # Load variables from .env file in the current directory
    load_dotenv()

    DOCUSEAL_URL = os.environ.get("DOCUSEAL_URL")
    API_KEY = os.environ.get("DOCUSEAL_API_KEY")
    TEMPLATE_ID = "1" # The template you created

    if not DOCUSEAL_URL or not API_KEY or "YOUR_API_KEY" in API_KEY:
        print("❌ Error: Please edit the .env file and set your DOCUSEAL_API_KEY.")
        return

    headers = {"X-Auth-Token": API_KEY}
    url = f"{DOCUSEAL_URL}/api/templates/{TEMPLATE_ID}"

    try:
        print(f"Connecting to {DOCUSEAL_URL}...")
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (like 401 or 404)

        print("✅ Successfully connected to DocuSeal!")
        template_data = response.json()
        fields = template_data.get("fields", [])

        if fields:
            print(f"\nFound the following fields on Template ID {TEMPLATE_ID}:")
            for field in fields:
                field_name = field.get('name')
                if field_name:
                    print(f"  - Name: '{field_name}', Type: {field.get('type')}")
            print("\nPlease use these 'Name' values in the main.py script.")
        else:
            print("\nTemplate found, but it has no fields defined. Please edit it in DocuSeal.")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Connection failed. Please check your .env file and network.")
        if e.response is not None:
            print(f"   Status Code: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
        else:
            print(f"   Error: {e}")

if __name__ == "__main__":
    verify_template()
