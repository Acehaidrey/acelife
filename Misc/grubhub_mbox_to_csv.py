"""
This script parses a Grubhub orders mbox file, extracts order details from the emails,
and saves them to a CSV file.

It can be run from the command line and accepts arguments for the input mbox file
and the output CSV file.

Example usage:
python email_parser.py --mbox-file /path/to/your/mbox/file --csv-file /path/to/your/output.csv
"""

import mailbox
import os
import re
import argparse
import pandas as pd
from bs4 import BeautifulSoup

DEFAULT_MBOX_FILE = '/Users/ace.haidrey/code/kraken/Takeout/Mail/Orders-Grubhub.mbox'
DEFAULT_CSV_FILE = '/Users/ace.haidrey/code/kraken/grubhub_orders.csv'

def extract_from_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    data = {}

    grubhub_data = soup.find('div', attrs={'data-section': 'grubhub-order-data'})
    if grubhub_data:
        restaurant_name_tag = grubhub_data.find('div', attrs={'data-field': 'restaurant-name'})
        data['restaurant_name'] = restaurant_name_tag.text.strip() if restaurant_name_tag else 'N/A'

        order_date_tag = grubhub_data.find('div', attrs={'data-field': 'scheduled-dt'})
        data['order_date'] = order_date_tag.text.strip() if order_date_tag else 'N/A'

        phone_number_tag = grubhub_data.find('div', attrs={'data-field': 'phone'})
        data['phone_number'] = phone_number_tag.text.strip() if phone_number_tag else 'N/A'

        address1_tag = grubhub_data.find('div', attrs={'data-field': 'address1'})
        address1 = address1_tag.text.strip() if address1_tag else ''
        city_tag = grubhub_data.find('div', attrs={'data-field': 'city'})
        city = city_tag.text.strip() if city_tag else ''
        state_tag = grubhub_data.find('div', attrs={'data-field': 'state'})
        state = state_tag.text.strip() if state_tag else ''
        zip_code_tag = grubhub_data.find('div', attrs={'data-field': 'zip'})
        zip_code = zip_code_tag.text.strip() if zip_code_tag else ''
        data['address'] = f"{address1}, {city}, {state} {zip_code}".strip(', ')

        delivery_fee_tag = grubhub_data.find('div', attrs={'data-field': 'delivery-charge'})
        data['delivery_fee'] = delivery_fee_tag.text.strip() if delivery_fee_tag else 'N/A'

        tip_tag = grubhub_data.find('div', attrs={'data-field': 'tip'})
        data['tip'] = tip_tag.text.strip() if tip_tag else 'N/A'

        tax_tag = grubhub_data.find('div', attrs={'data-field': 'sales-tax'})
        data['tax'] = tax_tag.text.strip() if tax_tag else 'N/A'

        subtotal_tag = grubhub_data.find('div', attrs={'data-field': 'subtotal'})
        data['subtotal'] = subtotal_tag.text.strip() if subtotal_tag else 'N/A'

        total_tag = grubhub_data.find('div', attrs={'data-field': 'total'})
        data['total'] = total_tag.text.strip() if total_tag else 'N/A'

    if not data.get('restaurant_name') or data.get('restaurant_name') == 'N/A':
        restaurant_name_tag = soup.find('strong')
        if restaurant_name_tag:
            data['restaurant_name'] = restaurant_name_tag.text.strip()

    order_number_match = re.search(r'Order: <strong>#(\d+ — \d+)<\/strong>', html_content)
    if order_number_match:
        data['order_number'] = order_number_match.group(1)

    deliver_to_tag = soup.find(string=re.compile(r'Deliver to:'))
    if deliver_to_tag:
        customer_name_tag = deliver_to_tag.find_next('div')
        if customer_name_tag:
            data['customer_name'] = customer_name_tag.text.strip()
    else:
        pickup_by_tag = soup.find(string=re.compile(r'Pickup by:'))
        if pickup_by_tag:
            customer_name_tag = pickup_by_tag.find_next('div')
            if customer_name_tag:
                data['customer_name'] = customer_name_tag.text.strip()

    return data

def main():
    parser = argparse.ArgumentParser(description='Parse Grubhub mbox files to a CSV.')
    parser.add_argument('--mbox-file', type=str, default=DEFAULT_MBOX_FILE,
                        help='Path to the mbox file to parse.')
    parser.add_argument('--csv-file', type=str, default=DEFAULT_CSV_FILE,
                        help='Path to save the output CSV file.')
    args = parser.parse_args()

    if not os.path.exists(args.mbox_file):
        print(f"Error: Mbox file not found at {args.mbox_file}")
        return

    mbox = mailbox.mbox(args.mbox_file)
    total_emails = len(mbox.keys())
    print(f"Processing {total_emails} emails from {args.mbox_file}...")

    extracted_data = []
    for i, message in enumerate(mbox):
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                if "text/html" in content_type:
                    try:
                        body = part.get_payload(decode=True).decode(errors='ignore')
                        data = extract_from_html(body)
                        extracted_data.append(data)
                    except Exception as e:
                        print(f"Could not decode or parse part in email {i+1}: {e}")
        else:
            try:
                body = message.get_payload(decode=True).decode(errors='ignore')
                data = extract_from_html(body)
                extracted_data.append(data)
            except Exception as e:
                print(f"Could not decode or parse message {i+1}: {e}")

    df = pd.DataFrame(extracted_data)
    df.to_csv(args.csv_file, index=False)
    print(f"Successfully processed {len(extracted_data)} emails and saved the data to {args.csv_file}")

if __name__ == "__main__":
    main()
