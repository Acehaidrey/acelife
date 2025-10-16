import mailbox
import re
import csv
from bs4 import BeautifulSoup, NavigableString
from email.utils import parsedate_to_datetime
from datetime import datetime

MBOX_FILE = '/Users/ace.haidrey/code/kraken/Takeout 2/Mail/Orders-Slice.mbox'
CSV_FILE = '/Users/ace.haidrey/code/kraken/extracted_orders.csv'


def get_email_body(soup):
    """Extracts the body of the email, handling forwarded messages."""
    blockquote = soup.find('blockquote')
    if blockquote:
        return BeautifulSoup(str(blockquote), 'html.parser')
    return soup


def parse_2019_layout(soup, details):
    """Parses the 2019 email layout."""
    customer_info_label = soup.find(string=re.compile('Customer information:'))
    if not customer_info_label:
        return None

    customer_info_container = customer_info_label.find_parent('table')

    # Extract name and phone
    customer_name_tag = customer_info_container.find('strong')
    if customer_name_tag:
        name_parts = customer_name_tag.get_text().strip().split()
        details['first_name'] = name_parts[0] if name_parts else None
        details['last_name'] = name_parts[1] if len(name_parts) > 1 else None

        phone_number_text = customer_info_container.get_text()
        phone_match = re.search(r'(\d{10})', phone_number_text)
        if phone_match:
            details['phone_number'] = phone_match.group(1)

    # Extract address
    address_lines = []
    address_table = customer_info_container.find_next_sibling('table')
    if address_table:
        tr_tag = address_table.find('tr')
        if tr_tag:
            for content in tr_tag.contents:
                if isinstance(content, NavigableString):
                    stripped_content = content.strip()
                    if stripped_content:
                        address_lines.append(stripped_content)

    if address_lines:
        details['address'] = ", ".join(address_lines)
    else:
        details['address'] = ""  # No address for pickup orders
    return details


def parse_modern_layout(soup, details):
    """Parses the modern email layout."""
    customer_info_td = soup.find('td', class_='order-transmission__meta-double')
    if not customer_info_td:
        return None

    customer_name_tag = customer_info_td.find('strong')
    if customer_name_tag:
        name_parts = customer_name_tag.get_text().strip().split()
        if name_parts and "Instructions" not in name_parts[0]:
            details['first_name'] = name_parts[0]
            details['last_name'] = name_parts[1] if len(name_parts) > 1 else None

    # Find phone number
    phone_number_tag = customer_info_td.find('a', href=re.compile(r'tel:(\d+)'))
    if phone_number_tag:
        details['phone_number'] = phone_number_tag.string.strip()
    else:
        # Fallback for phone number if not in <a> tag, look for 10 digits in the text directly within customer_info_td
        phone_match = re.search(r'(\d{10})', customer_info_td.get_text())
        if phone_match:
            details['phone_number'] = phone_match.group(1)

    # Address extraction
    address_lines = []

    # Find the table that contains the customer name and phone number
    name_phone_strong_tag = customer_info_td.find('strong')
    name_phone_table = None
    if name_phone_strong_tag:
        name_phone_table = name_phone_strong_tag.find_parent('table', class_='row')

    if name_phone_table:
        # The address is in the next sibling table
        address_table = name_phone_table.find_next_sibling('table', class_='row')
        if address_table:
            # Extract text directly from the <tr> within the address_table
            tr_tag = address_table.find('tr')
            if tr_tag:
                for content in tr_tag.contents:
                    if isinstance(content, NavigableString):
                        stripped_content = content.strip()
                        if stripped_content:
                            address_lines.append(stripped_content)

    if address_lines:
        details['address'] = ", ".join(address_lines)
    else:
        details['address'] = ""  # No address for pickup orders
    return details


def extract_order_info(soup, email_date):
    details = {}
    # Try each layout parser until one returns data
    parsers = [parse_2019_layout, parse_modern_layout]
    for parser in parsers:
        # Pass the same details dictionary to each parser
        parsed_details = parser(soup, details)
        if parsed_details:
            details.update(parsed_details)
            # Only break if a valid phone number is found (not the default Slice number)
            if details.get('phone_number') and details.get('phone_number') != '1-888-974-9928':
                break
    return details


def extract_order_info_from_html(html_content, email_date):
    """Parses the HTML content of an email to extract order details."""
    soup = BeautifulSoup(html_content, 'html.parser')
    soup = get_email_body(soup)
    details = extract_order_info(soup, email_date)

    # Restaurant Name
    restaurant_name_tag = soup.find('span', class_='order-transmission__header-shop-name')
    if restaurant_name_tag:
        details['restaurant_name'] = restaurant_name_tag.string.strip()

    # Order Number
    order_number_tag = soup.find(string=re.compile(r'Order:.*?(\d+)'))
    if order_number_tag:
        match = re.search(r'Order:.*?(\d+)', order_number_tag)
        if match:
            details['order_number'] = match.group(1)
    else:
        order_number_tag = soup.find('span', class_="order-transmission__blue")
        if order_number_tag:
            details['order_number'] = order_number_tag.string.strip()

    # Order Date, Day of Week, Order Time
    order_date_tag = soup.find(string=re.compile(r'(\w+), (\w+ \d+) at (\d+:\d+ \w+)'))
    if order_date_tag:
        match = re.search(r'(\w+), (\w+ \d+) at (\d+:\d+ \w+)', order_date_tag)
        if match:
            details['day_of_week'] = match.group(1)
            order_month_day = match.group(2)
            order_time_str = match.group(3)

            year = email_date.year
            order_month = datetime.strptime(order_month_day.split()[0], '%b').month

            if email_date.month == 1 and order_month == 12:
                year -= 1

            date_str = f"{order_month_day}, {year} {order_time_str}"
            try:
                dt_object = datetime.strptime(date_str, '%b %d, %Y %I:%M %p')
                details['order_date'] = dt_object.strftime('%Y-%m-%d')
                details['order_time'] = dt_object.strftime('%H:%M:%S')
            except ValueError as e:
                print(f"Error parsing date: {date_str} - {e}")
                details['order_date'] = None
                details['order_time'] = None

    # Subtotal, Tax, Tip, Delivery Fee, Total, Coupon Discount
    def get_price(label):
        label_tag = soup.find(string=re.compile(label))
        if label_tag:
            price_tag = label_tag.find_next('td')
            if price_tag:
                return price_tag.text.strip()
            price_tag = label_tag.find_next('p')
            if price_tag:
                return price_tag.text.strip()
        return None

    details['subtotal'] = get_price('Subtotal:')
    details['tax'] = get_price('Tax:')
    details['tip'] = get_price('Tip:')
    details['delivery_fee'] = get_price('Delivery Fee:')
    details['coupon_discount'] = get_price('Coupon Discount:')
    details['discount_percent'] = get_price('Discount Percent:')

    total_paid_tag = soup.find(string=re.compile('Total Paid to Restaurant'))
    if total_paid_tag:
        total_paid_price_tag = total_paid_tag.find_next('strong')
        if total_paid_price_tag:
            details['total'] = total_paid_price_tag.string.strip()
    else:
        details['total'] = get_price('Total')

    # Payment Method and Last 4 Digits
    payment_method_tag = soup.find('span', class_='order-transmission__meta-desc', string=re.compile(r'CREDIT|CASH'))
    if payment_method_tag:
        details['payment_method'] = payment_method_tag.string.strip()
        if details['payment_method'] == 'CREDIT':
            last_4_tag = soup.find(string=re.compile(r'ending in \d{4}'))
            if last_4_tag:
                match = re.search(r'ending in (\d{4})', last_4_tag)
                if match:
                    details['last_4_digits'] = match.group(1)

    return details


def process_all_emails(mbox_file):
    """
    Reads all emails from an mbox file and extracts order details.
    """
    mbox = mailbox.mbox(mbox_file)
    all_orders = []

    for message in mbox:
        email_date = parsedate_to_datetime(message['Date'])

        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                if "text/html" in content_type:
                    html_content = part.get_payload(decode=True)
                    try:
                        html_content_decoded = html_content.decode('utf-8')
                    except UnicodeDecodeError:
                        html_content_decoded = html_content.decode('latin-1')

                    html_details = extract_order_info_from_html(html_content_decoded, email_date)

                    if html_details:
                        all_orders.append(html_details)

                    break

    return all_orders


def save_to_csv(orders, csv_file):
    """Saves the extracted order details to a CSV file after removing duplicates."""
    if not orders:
        print("No orders to save.")
        return

    seen = set()
    unique_orders = []
    for order in orders:
        order_tuple = tuple(sorted(order.items()))
        if order_tuple not in seen:
            seen.add(order_tuple)
            unique_orders.append(order)

    fieldnames = ['restaurant_name', 'order_number', 'day_of_week', 'order_date', 'order_time', 'first_name',
                  'last_name', 'phone_number', 'address', 'subtotal', 'tax', 'tip', 'delivery_fee', 'coupon_discount',
                  'discount_percent', 'total', 'payment_method', 'last_4_digits']
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(unique_orders)
    print(f"Saved {len(unique_orders)} unique orders to {csv_file}")


if __name__ == "__main__":
    extracted_orders = process_all_emails(MBOX_FILE)
    save_to_csv(extracted_orders, CSV_FILE)