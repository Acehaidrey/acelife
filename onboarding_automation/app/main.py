
import os
import argparse
import requests
import json
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
DOCUSEAL_URL = os.environ.get("DOCUSEAL_URL")
API_KEY = os.environ.get("DOCUSEAL_API_KEY")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def get_all_templates():
    """Fetches all templates from the DocuSeal API."""
    try:
        headers = {"X-Auth-Token": API_KEY}
        response = requests.get(f"{DOCUSEAL_URL}/api/templates", headers=headers)
        response.raise_for_status()
        return response.json()['data']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching templates: {e}")
        return []

def create_submission(template_id, signer_email, signer_name, field_data):
    """Creates a single submission from a template."""
    try:
        headers = {"X-Auth-Token": API_KEY, "Content-Type": "application/json"}
        payload = {
            "template_id": template_id,
            "submitters": [{
                "name": signer_name,
                "email": signer_email,
                "role": "First Party",
                "values": field_data
            }]
        }
        response = requests.post(f"{DOCUSEAL_URL}/api/submissions", headers=headers, json=payload)
        response.raise_for_status()
        print(f"✅ Successfully sent template ID {template_id} to {signer_email}.")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error for template ID {template_id}: {e.response.text}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Onboard an employee for one or more restaurants.")
    # Required info
    parser.add_argument("--restaurant", required=True, choices=['ameci', 'aroma', 'both'], help="The restaurant the employee belongs to.")
    parser.add_argument("--name", required=True, help="Full name of the employee.")
    parser.add_argument("--email", required=True, help="Employee's email.")
    parser.add_argument("--first-day", required=True, help="Employee's first day of employment.")

    # Optional info (if you want to pre-fill it, otherwise the employee will be forced to)
    parser.add_argument("--address", help="Optional: Employee's street address.")
    parser.add_argument("--city-state-zip", help="Optional: Employee's city, state, and ZIP code.")
    parser.add_argument("--ssn", help="Optional: Employee's Social Security Number.")
    parser.add_argument("--filing-status", help="Optional: Employee's tax filing status.")

    args = parser.parse_args()

    with open(CONFIG_PATH, 'r') as f:
        restaurant_configs = json.load(f)

    print("Fetching all templates from DocuSeal...")
    all_templates = get_all_templates()
    if not all_templates:
        print("Could not retrieve templates. Exiting.")
        return

    templates_to_send = []
    if args.restaurant == 'ameci':
        prefixes = ('SHARED', 'AMECI')
    elif args.restaurant == 'aroma':
        prefixes = ('SHARED', 'AROMA')
    else: # both
        prefixes = ('SHARED', 'AMECI', 'AROMA')
    
    for template in all_templates:
        if template['name'].upper().startswith(prefixes):
            templates_to_send.append(template)

    print(f"Found {len(templates_to_send)} documents to send for restaurant selection: '{args.restaurant}'.")

    employer_key = 'ameci' if args.restaurant in ['ameci', 'both'] else 'aroma'
    employer_config = restaurant_configs[employer_key]

    # Start building the data payload with information we always have
    try:
        first_name, last_name = args.name.split(" ", 1)
    except ValueError:
        first_name = args.name
        last_name = ""

    field_data = {
        "first_name": first_name,
        "last_name": last_name,
        "employer_info": employer_config['employer_name_address'],
        "employer_ein": employer_config['employer_ein'],
        "first_date_of_employment": args.first_day
    }

    # Add optional fields to the payload ONLY if they were provided on the command line
    if args.address:
        field_data['address'] = args.address
    if args.city_state_zip:
        field_data['city_state_zip'] = args.city_state_zip
    if args.ssn:
        field_data['ssn'] = args.ssn
    if args.filing_status:
        field_data['filing_status'] = args.filing_status

    print(f"--- Starting onboarding for {args.name} ---")
    for template in templates_to_send:
        print(f"Sending template: '{template['name']}' (ID: {template['id']})")
        create_submission(template['id'], args.email, args.name, field_data)
    
    print("--- Process complete ---")

if __name__ == "__main__":
    main()
