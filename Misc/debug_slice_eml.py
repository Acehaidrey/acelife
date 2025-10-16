import mailbox
import os
from email.utils import parsedate_to_datetime

MBOX_FILE = '/Users/ace.haidrey/code/kraken/Takeout 2/Mail/Orders-Slice.mbox'


def find_specific_emails_and_print_html(mbox_file):
    """Finds specific emails and prints their HTML content."""
    mbox = mailbox.mbox(mbox_file)
    order_ids = ['138860671']

    for message in mbox:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == 'text/html':
                    html_content = part.get_payload(decode=True)
                    try:
                        html_decoded = html_content.decode('utf-8')
                    except UnicodeDecodeError:
                        html_decoded = html_content.decode('latin-1')

                    for order_id in order_ids:
                        if order_id in html_decoded:
                            print(f"--- Found email for order {order_id} ---")
                            print(html_decoded)
                            order_ids.remove(order_id)
                            break
        if not order_ids:
            break


if __name__ == "__main__":
    find_specific_emails_and_print_html(MBOX_FILE)