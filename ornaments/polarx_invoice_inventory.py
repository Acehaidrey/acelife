import csv
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd
import requests
import math

from collections import defaultdict

DESCRIPTION = """
This festive and thoughtful ornament is perfect for adding to any tree! Each ornament is personalized for free with names, years, and sometimes additional writing. Please specify precisely where you’d like each name to go. Otherwise our talented artists always use their best judgement to make your ornament special. The ornaments are personalized with permanent ink by hand.
[Disclaimer] It is your responsibility to ensure the spelling you give us is correct. Double check all spelling because if an issue occurs, we will not be able to replace it. If you’d like to forgo personalization, just write “No Personalization” in the box.
Please also note, the color scheme, design, and all that you see in the first image for the ornament cannot be altered. They come pre made that way.
Orders with confusing or unclear instructions may be delayed until we are able to reconnect with you to verify the desired personalization. If we cannot reach you in a timely manner, we will send the ornament with our best judgement or without personalization and we will not refund for this case either.
Thank you!
"""


def rename_files_in_directory(directory, prefix="RM"):
    # Traverse through the directory
    for filename in os.listdir(directory):
        # Check if the file is a jpg or png and does not start with the given prefix
        if (filename.endswith(".jpg") or filename.endswith(".png")) and not filename.startswith(prefix):
            # Split the filename and its extension
            name, ext = os.path.splitext(filename)

            # Convert the name to uppercase and add the prefix
            new_name = f"{prefix}{name.upper()}{ext}"

            # Get the full path for both the old and new file names
            old_path = os.path.join(directory, filename)
            new_path = os.path.join(directory, new_name)

            # Rename the file
            os.rename(old_path, new_path)
            print(f"Renamed: {filename} -> {new_name}")


def extract_item_number(item_name):
    """Extracts the last group of text within parentheses from the item name.
    For example:
      - STICK ON - DOG ADD ON(4 - BLACK, 4 - BROWN, 4 - YELLOW) (OR858) returns OR858
      - COUPLES - REINDEER COUPLE W/SCARVES (OR826-2) returns OR826-2
    """
    matches = re.findall(r'\(([^)]+)\)', item_name)
    ret_val = matches[-1] if matches else item_name
    return ret_val.upper()


def normalize_text(value: str) -> str:
    return (value or "").upper()


def infer_categories(item_number: str, item_name: str) -> str:
    """Infer category hierarchy based on item number and name keywords."""
    number = normalize_text(item_number)
    name = normalize_text(item_name)

    categories: list[str] = []

    def add(category: str) -> None:
        if category and category not in categories:
            categories.append(category)

    if number.startswith("PBS"):
        add("Stocking (W3LQNKF77II35AUEVYTGCLXZ)")
        if "BABY" in name:
            add("Ornament > Baby")
            if number.endswith("-P") or "PINK" in name:
                add("Ornament > Baby > Baby Girl (Pink)")
            elif number.endswith("-B") or "BLUE" in name:
                add("Ornament > Baby > Baby Boy (Blue)")
            else:
                add("Ornament > Baby > Baby Neutral")
        return ", ".join(categories)

    if number.startswith("PF"):
        add("Ornament")
        add("Ornament > Picture Frame")
    else:
        add("Ornament")

    if "EXPECTING" in name or "PREGNANT" in name:
        add("Ornament > We're Expecting (Pregnancy)")

    if number.startswith("DECO") or "DECO" in name:
        add("Ornament > Personalization Supplies")

    if any(number.startswith(prefix) for prefix in ("NFL", "NBA", "MLB", "NHL", "NCAA", "MLS")):
        add("Ornament > Sports")

    if "COUPLE" in name or "COUPLES" in name:
        add("Ornament > Family of 2 (Couples)")

    if "BABY" in name:
        add("Ornament > Baby")
        if number.endswith("-P") or "PINK" in name:
            add("Ornament > Baby > Baby Girl (Pink)")
        elif number.endswith("-B") or "BLUE" in name:
            add("Ornament > Baby > Baby Boy (Blue)")
        elif any(suffix in number for suffix in ("-RG", "-GN", "-GR")) or any(
            keyword in name for keyword in ("NEUTRAL", "RED & GREEN", "TEAL")
        ):
            add("Ornament > Baby > Baby Neutral")
        else:
            add("Ornament > Baby > Baby Neutral")

    if "CHILD" in name or "KID" in name:
        add("Ornament > Child")

    if any(keyword in name for keyword in ("DOG", "CAT", "PET", "PAW", "ANIMAL", "WOOF", "WHO SAVED WHO")):
        add("Ornament > Pets/Animals")

    if any(
        keyword in name
        for keyword in (
            "SOCCER",
            "BASEBALL",
            "FOOTBALL",
            "BASKETBALL",
            "HOCKEY",
            "GOLF",
            "CHEER",
            "SPORT",
            "NFL",
            "NBA",
            "MLB",
            "NHL",
            "KARATE",
            "JOGGER",
        )
    ):
        add("Ornament > Sports")

    if any(
        keyword in name
        for keyword in (
            "NURSE",
            "DOCTOR",
            "TEACHER",
            "POLICE",
            "OFFICER",
            "FIREFIGHTER",
            "FIREMAN",
            "DENTIST",
            "CHEF",
            "ENGINEER",
            "ARMY",
            "NAVY",
            "MARINE",
            "PILOT",
            "MILITARY",
            "OCCUPATION",
        )
    ):
        add("Ornament > Occupation")

    if any(
        keyword in name
        for keyword in (
            "BIKE",
            "CAMP",
            "FISH",
            "FISHING",
            "CAMPER",
            "CAMPING",
            "HUNT",
            "HUNTING",
            "SKI",
            "SNOWBOARD",
            "DANCE",
            "MUSIC",
            "GUITAR",
            "ORCHESTRA",
            "MOTORCYCLE",
            "MOTORBIKE",
            "ESPRESSO",
            "COFFEE",
            "CAMERA",
            "PHONE",
            "TECH",
            "GAMER",
        )
    ):
        add("Ornament > Hobbies/Activities")

    if "GENERAL" in name:
        add("Ornament > General")

    if "HOLIDAY" in name or "CHRISTMAS" in name or "XMAS" in name:
        add("Ornament > Holiday Themed")

    if any(
        keyword in name
        for keyword in (
            "TRAVEL",
            "POSTCARD",
            "SUITCASE",
            "VACATION",
            "ROAD TRIP",
            "ROADTRIP",
            "CAMPER",
            "RV",
        )
    ):
        add("Ornament > Travel")

    if any(keyword in name for keyword in ("HOUSE", "HOME", "DOOR", "FRONT DOOR")):
        add("Ornament > House/Door")

    family_size = None
    if "-" in number:
        suffix = number.split("-")[-1]
        if suffix.isdigit():
            family_size = int(suffix)
    if family_size is None and "FAMILY OF" in name:
        parts = name.split("FAMILY OF", 1)[-1].strip().split()
        if parts and parts[0].isdigit():
            family_size = int(parts[0])

    if family_size:
        if family_size == 2:
            add("Ornament > Family of 2 (Couples)")
        else:
            add(f"Ornament > Family of {family_size}")

    return ", ".join(categories)


def add_price_for_items(item_no):
    """
    Set pricing based on the item name
    """
    item_no = item_no.upper()

    # bags price
    if item_no.endswith('BAGS'):
        return 1.99

    # stocking price
    if item_no.startswith('PBS'):
        return 24.99

    # default ornament price
    price = 18.99

    # higher price for the NFL ornaments
    if item_no.startswith('NFL'):
        return 24.99

    # special handling for add ons
    addon_ids = ['OR2176-A', 'OR2177-A', 'OR2667', 'OR858', 'OR2013', 'OR2014']
    if item_no in addon_ids:
        return 5.99

    item_no_parts = item_no.split('-')

    # if item_no has some secondary value
    if len(item_no_parts) > 1:
        suffix = item_no_parts[-1]
        # non digit means its likely single regular ornament
        if not suffix.isdigit():
            return price

        _digit_val = int(suffix)
        # family of 2 or less regular price
        if _digit_val <= 2:
            return price
        # family of 3-5 is $1 more
        if 3 <= _digit_val <= 5:
            return price + 1
        # family of 6-7 is $2 more
        if 6 <= _digit_val <= 7:
            return price + 2
        # family of 8+ is $3 more
        if _digit_val >= 8:
            return price + 3

    return price


def format_invoice_received(csv_file_path, output_path=None):
    """
    Normalize invoice or style sheets so downstream catalog scripts can reuse them.

    Supports the original PolarX invoice export as well as simplified style sheets with
    STYLE/DESCRIPTION columns (e.g., newly ordered ornaments that are not yet in Square).
    """
    df = pd.read_csv(csv_file_path)
    normalized_columns = {col.strip().lower(): col for col in df.columns}

    standard_headers = {
        'product - description',
        'quantity',
        'price each',
        'amount',
        'sku',
    }

    if standard_headers.issubset(normalized_columns.keys()):
        csv_headers = [normalized_columns[h] for h in standard_headers]
        df = df[csv_headers]
        df = df.rename(columns={
            normalized_columns['product - description']: 'Name',
            normalized_columns['price each']: 'PricePerBox',
            normalized_columns['amount']: 'PriceTotal',
            normalized_columns['quantity']: 'Quantity',
            normalized_columns['sku']: 'SKU',
        })
        df['Name'] = df['Name'].str.upper()
        df['Number'] = df['Name'].apply(lambda x: x.split(' - ', 1)[0])

        def create_full_name(row):
            return format_item_name(row['Name'], row['Number'])

        df['FormattedName'] = df.apply(create_full_name, axis=1)
        df['Price'] = df['Number'].apply(add_price_for_items)
        df['TotalItemQuantity'] = np.where(
            df['Number'].str.startswith(('PF', 'OR')),
            df['Quantity'] * 12,
            df['Quantity']
        )
        df['PricePerItem'] = np.where(
            df['Number'].str.startswith(('PF', 'OR')),
            np.round(df['PricePerBox'] / 12, 2),
            df['Price']
        )

        df = df.sort_values('Number', ascending=True).reset_index(drop=True)
        df = df[[
            'Number', 'Name', 'FormattedName',
            'Quantity', 'TotalItemQuantity',
            'Price', 'PricePerItem', 'PricePerBox', 'PriceTotal', 'SKU'
        ]]
    elif {'style', 'description'}.issubset(normalized_columns.keys()):
        style_col = normalized_columns['style']
        description_col = normalized_columns['description']
        upc_col = normalized_columns.get('upc')
        amount_col = normalized_columns.get('amount')
        qty_col = normalized_columns.get('qty')
        already_exists_col = normalized_columns.get('already_exists')

        selected_cols = [style_col, description_col]
        if upc_col:
            selected_cols.append(upc_col)
        if amount_col:
            selected_cols.append(amount_col)
        if qty_col:
            selected_cols.append(qty_col)
        if already_exists_col:
            selected_cols.append(already_exists_col)

        df = df[selected_cols].copy()
        rename_map = {
            style_col: 'STYLE',
            description_col: 'DESCRIPTION',
        }
        if upc_col:
            rename_map[upc_col] = 'UPC'
        if amount_col:
            rename_map[amount_col] = 'AMOUNT'
        if qty_col:
            rename_map[qty_col] = 'QTY'
        if already_exists_col:
            rename_map[already_exists_col] = 'already_exists'

        df = df.rename(columns=rename_map)

        if 'already_exists' in df.columns:
            df = df[df['already_exists'].astype(str).str.lower().isin({'false', '0', 'no'})]

        df['Number'] = (
            df['STYLE']
            .astype(str)
            .apply(lambda x: re.sub(r'\s+', ' ', x.strip()).upper())
        )
        df['CleanDescription'] = (
            df['DESCRIPTION']
            .astype(str)
            .apply(lambda x: re.sub(r'\s+', ' ', x.strip()))
        )

        df = df[df['Number'] != ''].drop_duplicates('Number', keep='first')

        name_pairs = df.apply(
            lambda row: prepare_item_names(row['Number'], row['CleanDescription']),
            axis=1,
            result_type='expand'
        )
        df[['Name', 'FormattedName']] = name_pairs

        df['Price'] = df['Number'].apply(add_price_for_items).round(2)
        amount_series = df.get('AMOUNT', '').fillna('').astype(str)

        def parse_amount(val: str) -> float:
            cleaned = re.sub(r'[^0-9.\-]', '', val)
            return float(cleaned) if cleaned else 0.0

        df['PricePerBox'] = amount_series.apply(parse_amount).round(2)
        df['Quantity'] = pd.to_numeric(
            df.get('QTY', 0).fillna(0),
            errors='coerce'
        ).fillna(0).astype(int)

        items_per_box = np.where(df['Number'].str.startswith('OR'), 12, 1)
        with np.errstate(divide='ignore', invalid='ignore'):
            df['PricePerItem'] = np.where(
                items_per_box > 1,
                np.round(df['PricePerBox'] / items_per_box, 2),
                df['PricePerBox']
            )

        df['PricePerItem'] = np.round(df['PricePerItem'], 2)
        df['TotalItemQuantity'] = (df['Quantity'] * items_per_box).astype(int)
        df['PriceTotal'] = np.round(df['PricePerBox'] * df['Quantity'], 2)
        df['SKU'] = (
            df.get('UPC', '')
            .fillna('')
            .astype(str)
            .str.strip()
        )

        df = df[[
            'Number', 'Name', 'FormattedName', 'SKU',
            'Quantity', 'TotalItemQuantity',
            'Price', 'PricePerItem', 'PricePerBox', 'PriceTotal'
        ]].reset_index(drop=True)

        print(f'Prepared {len(df)} new style rows with zeroed counts.')
    else:
        raise ValueError(
            'Unrecognized invoice format. Expected standard PolarX invoice columns '
            "or a sheet containing 'STYLE' and 'DESCRIPTION'."
        )

    print('Here is a preview of the items:')
    print(df.head(10).to_string())
    output_path = output_path or csv_file_path.replace('.csv', '_OUTPUT.csv')
    df.to_csv(output_path, index=False)
    print(f'Writing cleaned up inventory csv to {output_path}')
    return output_path


def format_inventory_received(csv_file_path, output_path = None):
    """
    The inventory we received that we counted. There are duplicate items that need to be grouped.
    Compare this to the invoice sent to find which have more or less sent.
    """
    csv_headers = ['Ornament_Name', 'Box_Count']
    output_dict = defaultdict(lambda: 0)
    count, dups = 0, set()
    with open(csv_file_path) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            count += 1
            if row[0] not in csv_headers:
                try:
                    # print(', '.join(row))
                    _key = row[0].upper().strip().strip('_')  # to keep 0 prefix had to add _ in excel cell
                    _key = add_item_prefix(_key)
                    if _key in output_dict:
                        dups.add(_key)
                    output_dict[_key] += int(row[1].strip())
                except ValueError:
                    print(f'[Record Error] Could not parse count value: {row}.')
        print(f'Processed {len(output_dict.keys())} lines. Input Records Count: {count}. Found {len(dups)} duplicates.')
        # print(output_dict, dups)
    output_path = output_path or csv_file_path.strip('.csv') + '_OUTPUT.csv'
    with open(output_path, 'w+', newline='\n') as out_csvfile:
        csv_writer = csv.writer(out_csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(csv_headers)
        for key in sorted(output_dict.keys()):
            csv_writer.writerow([key, output_dict[key]])
        print(f'Wrote Output: {output_path}')
    return output_path


def compare_invoice_count_to_our_count(our_count_path, invoice_path, output_path = None):
    with open(our_count_path) as our_csv_file, open(invoice_path) as invoice_csv_file:
        our_csv_reader = csv.DictReader(our_csv_file)
        invoice_csv_reader = csv.DictReader(invoice_csv_file)
        our_dict, invoice_dict = defaultdict(lambda: 0), defaultdict(lambda: 0)
        for row in our_csv_reader:
            our_dict[row['Ornament_Name']] = int(float(row['Box_Count']))
        for row in invoice_csv_reader:
            invoice_dict[row['Number']] = int(float(row['Quantity'].strip().strip('ea')))
        # get overlap
        # get missing dates
        # build csv with the problematic records comparison
        print(our_dict)
        print(invoice_dict)
        keys_only_ours = our_dict.keys() - invoice_dict.keys()
        keys_only_theirs = invoice_dict.keys() - our_dict.keys()
        keys_overlapped = invoice_dict.keys() & our_dict.keys()
        print(sorted(list(keys_only_ours)))
        print(sorted(list(keys_only_theirs)))
        print(sorted(list(keys_overlapped)))
        print('-----')
        remove_prefix = {i.strip('OR').strip('PF') for i in keys_only_ours}.intersection({i.strip('OR').strip('PF')
                                                                                          for i in keys_only_theirs})
        print(remove_prefix)
        print('-------')
        output_path = output_path or os.path.join(os.path.expanduser('~'), 'Downloads', '2024_COMPARE_ORNAMENTS.csv')
        with open(output_path, 'w+', newline='\n') as out_csvfile:
            csv_writer = csv.DictWriter(out_csvfile, fieldnames=['Item Name', 'Invoice Count', 'True Count', 'Diff'])
            csv_writer.writeheader()
            for key in keys_overlapped:
                d = {
                    'Item Name': key,
                    'Invoice Count': invoice_dict[key],
                    'True Count': our_dict[key],
                    'Diff': our_dict[key] - invoice_dict[key]
                }
                csv_writer.writerow(d)
                print(d)
            for key in keys_only_theirs:
                d = {
                    'Item Name': key,
                    'Invoice Count': invoice_dict[key],
                    'True Count': 0,
                    'Diff': our_dict[key] - invoice_dict[key]
                }
                csv_writer.writerow(d)
                print(d)
        print(f'Writing output comparison file to {output_path}')
        return output_path


def add_item_prefix(item_id):
    item_id_upped = item_id.upper()
    if item_id_upped.startswith('OR'):
        item_id_upped = item_id_upped.replace('OR', '')
    if item_id_upped.startswith('PF'):
        item_id_upped = item_id_upped.replace('PF', '')
    pfs_purchased = {
        '1165-R', '1404', '1435', '1591-W/O STAMP', '1145', '1717', '2037', '2138', '2300', '600-B', '600-P', '600-RG',
        '2478-P', '2478-B', '1714-PEWTER', '2123', '1048',
    }
    prefix_ = 'OR' if item_id_upped not in pfs_purchased else 'PF'
    return prefix_ + item_id if not item_id.startswith(prefix_) else item_id


def find_missing_photos(folder_path, invoice_path):
    """Compare the photos given from fiver person to the items from invoice. Name comparison."""
    invoice_df = pd.read_csv(invoice_path)
    invoice_ids = set(invoice_df['Number'].unique())

    blank_path = os.path.join(folder_path, 'BlankImages')
    edited_path = os.path.join(folder_path, 'EditedImages')

    downloads_ids = set()
    for f in os.listdir(blank_path):
        # print(f)
        downloads_ids.add(f.strip('.jpg').strip('.png'))

    for f in os.listdir(edited_path):
        downloads_ids.add(f.strip('.jpg').strip('.png'))

    missing_items = invoice_ids - downloads_ids
    print(f'Invoice has {len(invoice_ids)} items. Downloads folder has {len(downloads_ids)} items.')
    if missing_items:
        print('Invoice ids: ' + str(sorted(list(invoice_ids))))
        print('Photo ids: ' + str(sorted(list(downloads_ids))))
        print(f'Missing ids: ({len(missing_items)} missing) ' + str(sorted(list(missing_items))))

    return missing_items


def format_item_name(item_name, item_no=None):
    """Formats an item name to ensure consistent styling and spacing."""

    # Initial formatting: uppercase, trim whitespace, and replace line breaks with spaces
    item_name = item_name.upper().strip().replace('\n', ' ')

    # Specific replacements
    item_name = item_name.replace('OR 1253-8', 'OR1253-8')
    item_name = item_name.replace('PICTUREFRAME', 'PICTURE FRAME')
    item_name = item_name.replace('W/OSTAMP', 'W/O STAMP')

    # replace multiple white space to just one
    item_name = re.sub(r'\s+', ' ', item_name).strip()

    # Split by whitespace and clean extra spaces
    item_name_list = [i.strip() for i in item_name.split() if i]

    # Add spaces around hyphens, but exclude specific cases
    if item_no and item_no.startswith(('OR', 'PF', 'RM')):
        # Create a regex pattern to match the beginning of the string with the
        # Number value followed by optional whitespace and '-'
        prefix_pattern = re.escape(item_no) + r'\s*-\s*'
        # Remove the prefix pattern from the beginning of fmt_desc
        cleaned_desc = re.sub(f'^{prefix_pattern}', '', ' '.join(item_name_list))

        formatted_list = []
        for i in cleaned_desc.split(' '):
            if '-' in i and not (i.startswith('(') and i.endswith(')')) and i not in ('T-REX', 'T-BALL'):
                # Split by hyphen and rejoin with spaces around it
                i = ' - '.join(i.split('-')).strip()
            formatted_list.append(i)

        # Combine cleaned description with the Number in parentheses
        item_name_list = formatted_list + [f" ({item_no.upper()})"]

    # Join all parts back into a single string
    formatted_name = ' '.join(item_name_list)

    # remove any multiple white spaces
    formatted_name = re.sub(r'\s+', ' ', formatted_name).strip()

    return formatted_name


def prepare_item_names(style_code: str, description: str) -> Tuple[str, str]:
    """Create the base and formatted name for a new catalog item."""
    style_clean = re.sub(r'\s+', ' ', (style_code or '').strip()).upper()
    if not style_clean:
        raise ValueError("Style code is required to build item names.")

    description_clean = re.sub(r'\s+', ' ', (description or '').strip())

    if style_clean.startswith(('OR', 'PF', 'RM')):
        base_name = f"{style_clean} - {description_clean}".strip(' -')
    else:
        base_name = description_clean or style_clean
        if base_name and style_clean not in base_name:
            base_name = f"{base_name} ({style_clean})"

    formatted_name = format_item_name(base_name, style_clean)
    return base_name, formatted_name


def rename_items_in_catalog(catalog_path, invoice_path):

    # read the invoice file into a dataframe
    invoice_df = pd.read_csv(invoice_path)
    print(invoice_df.head(1000).to_string())
    print(f'{len(invoice_df)} items found in invoice')

    # read the catalog into a dataframe
    catalog_df = pd.read_csv(catalog_path)
    # apply settings below to all
    catalog_df['Enabled Mission Viejo'] = 'Y'
    catalog_df['Enabled Cerritos'] = 'Y'
    catalog_df['Enabled Westminster'] = 'Y'
    catalog_df['Enabled Storage'] = 'Y'
    catalog_df['Tax - Sales Tax (7.75%)'] = 'Y'
    catalog_df['Delivery Enabled'] = 'Y'
    catalog_df['Pickup Enabled'] = 'Y'
    catalog_df['Shipping Enabled'] = 'Y'
    catalog_df['Item Type'] = 'Physical good'
    # Extract item numbers (will drop at end)
    catalog_df['ItemNumber'] = catalog_df['Item Name'].apply(extract_item_number)

    # Filter catalog_df to get only specific categories in 'Reporting Category' for ornaments and stockings
    non_categories = ['Sportula', 'Sportula Set', 'Piggy Bank', 'Pokemon']
    subset_df = catalog_df[~catalog_df['Reporting Category'].isin(non_categories) |
                           catalog_df['Reporting Category'].isnull() |
                           (catalog_df['Reporting Category'] == '')].copy()

    # For the personalization to only be for these types
    subset_df['Modifier Set - Personalization'] = 'Y'
    # Define the condition to check if 'ItemNumber' has a hyphen followed by a number greater than 2
    condition = subset_df['ItemNumber'].str.contains(r'-([3-9]|\d{2,})', regex=True)
    # Set 'Modifier Set - Additional Personalization (If Above Limited)' based on the condition
    subset_df['Modifier Set - Additional Personalization (If Above Limited)'] = np.where(condition, 'Y', 'N')

    # Update catalog_df with modified subset_df values
    catalog_df.update(subset_df)

    # Filter subset_df based on item numbers present in invoice_df
    subset_df = subset_df[subset_df['ItemNumber'].isin(invoice_df['Number'])]

    # Apply adjustments (example: enabling/disabling features based on other columns)
    subset_df['Square Online Item Visibility'] = 'visible'
    # set all to 0.5 lb so 8 oz for now
    subset_df['Weight (lb)'] = 0.5
    # Set 'Reporting Category' based on whether 'Item Name' begins with 'PBS'
    subset_df['Reporting Category'] = np.where(
        subset_df['Item Name'].str.startswith('PBS'),
        'Stocking',
        'Ornament'
    )
    subset_df['Description'] = DESCRIPTION.strip()

    # Create a mapping of Number to FormattedName from invoice_df
    name_mapping = dict(zip(invoice_df['Number'], invoice_df['FormattedName']))
    price_mapping = dict(zip(invoice_df['Number'], invoice_df['Price']))
    total_count_mapping = dict(zip(invoice_df['Number'], invoice_df['TotalItemQuantity']))

    # Update 'Item Name' in subset_df based on matching 'ItemNumber' with 'Number'
    subset_df['Item Name'] = subset_df['ItemNumber'].map(name_mapping).combine_first(subset_df['Item Name'])

    # Update 'Price' in subset_df based on matching 'ItemNumber' with 'Number'
    subset_df['Price'] = subset_df['ItemNumber'].map(price_mapping).combine_first(subset_df['Price'])

    # Use map to get the 'TotalItemCount' for each 'ItemNumber' in subset_df
    subset_df['TotalItemCount'] = subset_df['ItemNumber'].map(total_count_mapping)

    # update the current count at MV for all

    subset_df['New Quantity Mission Viejo'] = (subset_df['Current Quantity Mission Viejo'].fillna(0) +
                                               subset_df['TotalItemCount'].fillna(0))

    print(subset_df.to_string())

    # Drop TotalItemCount column
    subset_df = subset_df.drop(columns=['TotalItemCount'])

    print('-' * 100)
    # Get item names from invoice_df that are missing in subset_df
    missing_items = invoice_df[~invoice_df['Number'].isin(subset_df['ItemNumber'])]
    # Display or print the missing item names
    print(f"Missing items in subset_df: {len(missing_items)} items")
    print(missing_items[['Number', 'FormattedName']].to_string(index=False))
    print('-' * 100)

    # Update catalog_df with modified subset_df values
    catalog_df.update(subset_df)

    # multiple variation types
    multi_variations_df = subset_df[
        subset_df['ItemNumber'].str.contains('-A') &  # Condition 1: ItemNumber contains '-A'
        (subset_df['Item Name'].str.contains('EACH') | subset_df['Item Name'].str.contains('STICK ON'))
        # Condition 2: Item Name contains 'EACH' or 'STICK ON'
        ]['ItemNumber'].unique()
    print(multi_variations_df)
    print(f'{len(multi_variations_df)} ornaments with multiple types found')
    print('-' * 100)

    # catalog GTIN sometimes is a float - needs to be an int
    catalog_df['GTIN'] = catalog_df['GTIN'].astype('Int64')

    # Write the full updated catalog back to CSV (drop item number column)
    catalog_df = catalog_df.drop(columns=['ItemNumber'])
    output_path = catalog_path.strip('.csv') + '_CLEANEDUP.csv'
    catalog_df.to_csv(output_path, index=False)
    print("Catalog updated successfully.")
    return output_path


def download_photo_to_temp(url: str, suffix: str = ".jpg") -> Path:
    """
    Download a photo from the given URL and store it in a temporary file.
    Returns the Path to the downloaded file.
    """
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(tmp_fd)
    path_obj = Path(tmp_path)
    path_obj.write_bytes(response.content)
    return path_obj


def upload_photo_to_square(
    client,
    item_id: str,
    short_name: str,
    full_name: str,
    local_path: Path,
    edited: bool = False,
):
    """
    Upload a photo from a local file to Square's catalog for the given item.
    """
    image_id = f"#{short_name}"
    caption = full_name
    if edited:
        image_id += " EDITED"
        caption += " EDITED"

    with local_path.open("rb") as image_file:
        result = client.catalog.create_catalog_image(
            request={
                "idempotency_key": str(time.time()),
                "object_id": item_id,
                "image": {
                    "type": "IMAGE",
                    "id": image_id,
                    "image_data": {
                        "caption": caption
                    }
                }
            },
            image_file=image_file
        )
    if result.is_error():
        raise RuntimeError(result.errors)
    return result.body


def upload_photos_from_url_list(
    client,
    photo_csv_path: str,
    style_column: str = "STYLE",
    url_column: str = "photo_url",
    caption_column: str = "FormattedName",
    edited: bool = False,
    skip_existing: bool = True,
) -> None:
    """
    Reads a CSV that contains item style codes and photo URLs.
    Finds each item in Square using text search, and uploads the corresponding photo.
    CSV must contain columns:
      - STYLE (or specified via style_column) e.g., 'OR2905-4'
      - photo_url (or specified url_column) with a publicly accessible image URL
      - Optional: FormattedName or similar (used for caption; defaults to STYLE if missing)

    Set skip_existing=False to force re-uploading even if the item already has image_ids.
    """
    df = pd.read_csv(photo_csv_path)
    missing_columns = {style_column, url_column} - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns in CSV: {', '.join(missing_columns)}")

    total_rows = len(df)
    successes = 0
    skipped = 0
    failures = []

    for row_index, row in df.iterrows():
        style_code = str(row[style_column]).strip()
        photo_url = str(row[url_column]).strip()
        if not style_code or not photo_url:
            print(f"[{row_index + 1}/{total_rows}] Skipping {style_code or '(missing style)'}: no photo URL.", flush=True)
            continue
        print(f"[{row_index + 1}/{total_rows}] Processing {style_code} -> {photo_url}", flush=True)

        caption_value = row.get(caption_column, style_code)
        short_name = style_code.upper()

        # Search for the Square item
        try:
            resp = client.catalog.search_catalog_items(
                body={"text_filter": short_name}
            ).body
            items = resp.get("items", [])
            found_names = [item["item_data"]["name"] for item in items]
            print(f"  Search returned {len(items)} item(s): {found_names}", flush=True)
        except Exception as exc:
            failures.append((style_code, photo_url, f"search error: {exc}"))
            print(f"  Search error for {style_code}: {exc}", flush=True)
            continue

        if not items:
            failures.append((style_code, photo_url, "no catalog items found"))
            print(f"  No catalog items found for {style_code}.", flush=True)
            continue

        # pick the best candidate
        matched_item = None
        if len(items) == 1:
            matched_item = items[0]
        else:
            for candidate in items:
                candidate_name = extract_item_number(candidate["item_data"]["name"])
                if candidate_name.upper() == short_name:
                    matched_item = candidate
                    break
            if matched_item is None:
                failures.append((style_code, photo_url, f"multiple matches: {[item['item_data']['name'] for item in items]}"))
                continue

        print(f"  Matched catalog item: {matched_item['item_data']['name']} ({matched_item['id']})", flush=True)

        existing_images = matched_item["item_data"].get("image_ids") or []
        if skip_existing and existing_images:
            print(f"  Skipping {style_code}: item already has {len(existing_images)} image(s).", flush=True)
            skipped += 1
            continue

        try:
            local_path = download_photo_to_temp(photo_url)
            print(f"  Downloaded photo to {local_path}", flush=True)
        except Exception as exc:
            failures.append((style_code, photo_url, f"download failed: {exc}"))
            print(f"  Download failed for {style_code}: {exc}", flush=True)
            continue

        item_id = matched_item["id"]
        item_name = matched_item["item_data"]["name"]
        short_item_name = extract_item_number(item_name)

        try:
            print(f"  Uploading photo for {style_code}", flush=True)
            upload_photo_to_square(
                client=client,
                item_id=item_id,
                short_name=short_item_name,
                full_name=item_name,
                local_path=local_path,
                edited=edited,
            )
            successes += 1
            print(f"  Upload succeeded for {style_code}", flush=True)
        except Exception as exc:
            failures.append((style_code, photo_url, f"upload failed: {exc}"))
            print(f"  Upload failed for {style_code}: {exc}", flush=True)
        finally:
            try:
                if local_path.exists():
                    local_path.unlink()
                    print(f"  Removed temp file {local_path}", flush=True)
            except OSError:
                pass

    print(f"Processed {total_rows} rows. Uploaded {successes} images. Skipped {skipped}. Failures: {len(failures)}.", flush=True)
    if failures:
        print("Failed uploads:")
        for style, url, reason in failures:
            print(f"  {style} -> {url} ({reason})")
def get_square_client(token):
    from square.client import Client
    from square.http.auth.o_auth_2 import BearerAuthCredentials

    app_id = os.getenv('APPLICATION_ID', 'sq0idp-C1hXP_-BckAJmTaP0cnwiQ')
    client = Client(
        bearer_auth_credentials=BearerAuthCredentials(
            access_token=os.environ.get('SQUARE_ACCESS_TOKEN', token)
        ),
        environment='production')
    return client


def get_all_catalog_items(client):
    all_items = []
    cursor = 'start'
    while cursor:
        if cursor == 'start':
            cursor = None
        raw_return = client.catalog.list_catalog(types='ITEM', cursor=cursor)
        items = raw_return.body['objects']
        all_items.extend(items)
        cursor = raw_return.body['cursor'] if 'cursor' in raw_return.body.keys() else None
        print(f'Added {len(items)} items. Cursor is: {cursor}')
    print(f'Total number of items found {len(all_items)}')
    return all_items


def get_all_catalog_items_missing_images(client):
    all_items = []
    cursor = 'start'
    while cursor:
        if cursor == 'start':
            cursor = None
        raw_return = client.catalog.list_catalog(types='ITEM', cursor=cursor)
        items = raw_return.body['objects']
        items_missing_images = [i for i in items if not i['item_data'].get('image_ids', None)] # ['item_data']['name']
        all_items.extend(items_missing_images)
        cursor = raw_return.body['cursor'] if 'cursor' in raw_return.body.keys() else None
        print(f'Added {len(items)} items. Cursor is: {cursor}')
    print(f'Total number of items found {len(all_items)} missing any images.')
    df = pd.DataFrame(all_items)
    print(df.to_string())
    return all_items


def get_all_items_in_given_year(client, items, year_filter=2024):
    items = items or get_all_catalog_items(client)

    from datetime import datetime

    recent_items = []
    for item in items:
        created_at = item['created_at']
        try:
            created_at_dt = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            created_at_dt = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ')
        yr = created_at_dt.year
        if yr == year_filter:
            recent_items.append(item)
    print(f'Total number of items found {len(recent_items)}')
    return recent_items


def update_photos_of_items(client, fiver_photo_downloaded_path, edited=False):

    found_items = []
    for f in os.listdir(fiver_photo_downloaded_path):
        image_id = f.strip('.jpg').strip('.png')
        req = client.catalog.search_catalog_items(body={"text_filter": image_id}).body
        try:
            items = req['items']
            print(f'For id {image_id} found {len(items)} items in catalog')
        except KeyError:
            print(f'ERROR: No results for {image_id}')
            items = []
        for item in items:
            item_id = item['id']
            item_name = item['item_data']['name']
            short_item_name = extract_item_number(item_name)
            found_items.extend(short_item_name)
            print(image_id, item_id, item_name, short_item_name)
            # if the length is 1 to automatically assign to this
            # if there are multiple catalog items found matching, then just use the one exact match
            # i.e. if have OR1739, and also finds OR1739-2, OR1739-4, etc. and just want OR1739
            if len(items) == 1 or image_id == short_item_name:
                print(f'Inserting image for item id {image_id}, short name {short_item_name}, {item_id}')
                id = f"#{short_item_name}"
                caption = item_name
                if edited:
                    id += ' EDITED'
                    caption += ' EDITED'
                result = client.catalog.create_catalog_image(
                    request={
                        "idempotency_key": str(time.time()),
                        "object_id": item_id,
                        "image": {
                            "type": "IMAGE",
                            "id": id,
                            "image_data": {
                                "caption": caption
                            }
                        }
                    },
                    image_file=open(os.path.join(fiver_photo_downloaded_path, f), 'rb')
                )
                if result.is_error():
                    print(f'ERROR {image_id}, {item_name}, {result.errors}')
    return found_items


def fill_missing_update_photos_of_items(client, fiver_photo_downloaded_path):
    items_missing_images = get_all_catalog_items_missing_images(client)
    all_images_in_folder = os.listdir(fiver_photo_downloaded_path)
    still_missing = []
    for item in items_missing_images:
        item_id = item['id']
        item_name = item['item_data']['name']
        short_item_name = extract_item_number(item_name)
        image_id = short_item_name + '.jpg'
        print(image_id, item_id, item_name, short_item_name)
        if image_id in all_images_in_folder:
            result = client.catalog.create_catalog_image(
                request={
                    "idempotency_key": str(time.time()),
                    "object_id": item_id,
                    "image": {
                        "type": "IMAGE",
                        "id": f"#{short_item_name}",
                        "image_data": {
                            "caption": item_name
                        }
                    }
                },
                image_file=open(os.path.join(fiver_photo_downloaded_path, image_id), 'rb')
            )
            if result.is_error():
                print(f'ERROR {image_id}, {item_name}, {result.errors}')
        else:
            print(f'ERROR {image_id} not found. {item_name}')
            still_missing.append(item_name)
    return still_missing

def format_rm_inventory_received(rm_count_path, output_path=None):
    df = pd.read_csv(rm_count_path)
    print(df.to_string())

    df = df.rename(columns={
        'Name': 'Ornament_Name',
    })
    df['Box_Count'] = df['Item Count'] / 12
    df['Ornament_Name'] = df['Ornament_Name'].apply(lambda x: f'RM{x}' if not x.startswith('RM') else x)

    df = df[['Ornament_Name', 'Box_Count']]

    print('Here is a preview of the items:')
    print(df.to_string())
    output_path = output_path or rm_count_path.replace('.csv', '_OUTPUT.csv')
    df.to_csv(output_path)
    print(f'Writing cleaned up inventory csv to {output_path}')
    return output_path


def format_rm_invoice_received(rm_invoice_path, output_path=None):
    # call rename_items_in_catalog() with upc info too
    # add record if item doesnt exist
    # update record if it does exist with the count
    # update the photos as well
    df = pd.read_csv(rm_invoice_path)
    df = df.rename(columns={
        'Item Number': 'SKU',
        'Item Description': 'Name',
        'Item ID': 'Number',
        'Extension': 'PriceTotal',
        'Unit Price': 'PricePerItem',
    })
    df['Name'] = df['Name'].str.upper()
    df['Number'] = df['Number'].apply(lambda x: f'RM{x}'if not x.startswith('RM') else x)
    df['TotalItemQuantity'] = df['Shipped Qty']
    df['Quantity'] = df['Shipped Qty']/12
    df['PricePerBox'] = df['PricePerItem'] * 12

    def create_full_name(row):
        return format_item_name(row['Name'], row['Number'])

    df['FormattedName'] = df.apply(create_full_name, axis=1)
    df['Price'] = df['Number'].apply(add_price_for_items)

    df = df.sort_values('Number', ascending=True).reset_index()

    df = df[[
        'Number', 'Name', 'FormattedName', 'SKU',
        'Quantity', 'TotalItemQuantity',
        'Price', 'PricePerItem', 'PricePerBox', 'PriceTotal',
    ]]

    # remove the bags item
    df = df[~df['Number'].isin(['RMBAGS'])]

    print('Here is a preview of the items:')
    print(df.head(50).to_string())
    output_path = output_path or rm_invoice_path.replace('.csv', '_OUTPUT.csv')
    df.to_csv(output_path)
    print(f'Writing cleaned up inventory csv to {output_path}')
    return output_path


def format_rm2025_inventory_received(rm_inventory_path, output_path=None):
    """Format rm2025.csv inventory into the same shape expected by catalog updates."""
    df = pd.read_csv(rm_inventory_path)
    normalized_columns = {col.strip().lower(): col for col in df.columns}

    required_columns = {'sku', 'description', 'qty'}
    if not required_columns.issubset(normalized_columns.keys()):
        missing = required_columns - set(normalized_columns.keys())
        raise ValueError(f"Missing required columns in {rm_inventory_path}: {', '.join(sorted(missing))}")

    df = df.rename(columns={
        normalized_columns['sku']: 'SKU',
        normalized_columns['description']: 'Description',
        normalized_columns['qty']: 'Qty',
    })
    upc_col = normalized_columns.get('upc code')

    df['Number'] = df['SKU'].astype(str).apply(lambda x: f'RM{x}' if not str(x).startswith('RM') else str(x))
    df['CleanDescription'] = (
        df['Description']
        .astype(str)
        .apply(lambda x: re.sub(r'\s+', ' ', x.strip()))
        .apply(lambda x: re.sub(r'\s+ea\s*$', '', x, flags=re.IGNORECASE))
    )

    name_pairs = df.apply(
        lambda row: prepare_item_names(row['Number'], row['CleanDescription']),
        axis=1,
        result_type='expand'
    )
    df[['Name', 'FormattedName']] = name_pairs

    df['Price'] = df['Number'].apply(add_price_for_items)
    df['TotalItemQuantity'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(0).astype(int)
    df['Quantity'] = df['TotalItemQuantity']
    if upc_col:
        df['SKU'] = (
            df[upc_col]
            .astype(str)
            .apply(lambda x: re.sub(r'\s+', '', x.strip()))
        )
    else:
        df['SKU'] = df['Number']

    df = df.sort_values('Number', ascending=True).reset_index(drop=True)
    df = df[[
        'Number', 'Name', 'FormattedName', 'SKU',
        'Quantity', 'TotalItemQuantity', 'Price',
    ]]

    print('Here is a preview of the items:')
    print(df.head(50).to_string())
    output_path = output_path or rm_inventory_path.replace('.csv', '_OUTPUT.csv')
    df.to_csv(output_path, index=False)
    print(f'Writing cleaned up inventory csv to {output_path}')
    return output_path


def write_missing_rows_from_catalog(catalog_path, invoice_path, output_path=None):
    """Write only the catalog rows that correspond to the invoice items."""
    invoice_df = pd.read_csv(invoice_path)
    catalog_df = pd.read_csv(catalog_path)
    catalog_df['ItemNumber'] = catalog_df['Item Name'].apply(extract_item_number)

    missing_rows = catalog_df[catalog_df['ItemNumber'].isin(invoice_df['Number'])].copy()
    quantity_map = dict(
        zip(
            invoice_df['Number'],
            pd.to_numeric(invoice_df.get('TotalItemQuantity', 0), errors='coerce')
            .fillna(0)
            .astype(int),
        )
    )
    missing_rows.loc[:, 'Categories'] = missing_rows.apply(
        lambda row: infer_categories(str(row['ItemNumber']), str(row['Item Name'])),
        axis=1,
    )
    missing_rows.loc[:, 'New Quantity Cerritos'] = missing_rows['ItemNumber'].apply(
        lambda num: int(quantity_map.get(num, 0) // 2)
    )
    missing_rows.loc[:, 'New Quantity Mission Viejo'] = missing_rows['ItemNumber'].apply(
        lambda num: int(math.ceil(quantity_map.get(num, 0) / 2))
    )
    if 'ItemNumber' in missing_rows.columns:
        missing_rows = missing_rows.drop(columns=['ItemNumber'])

    output_path = output_path or catalog_path.replace('.csv', '_MISSING_ONLY.csv')
    missing_rows.to_csv(output_path, index=False)
    print(f'Wrote missing-only catalog rows to {output_path}')
    return output_path


def upload_missing_item_photos(
    client,
    photo_dir: str,
    missing_rows_csv: str,
    skip_existing: bool = True,
) -> None:
    """Upload photos from a directory for the items listed in missing_rows_csv."""
    df = pd.read_csv(missing_rows_csv)
    if "Item Name" not in df.columns:
        raise ValueError("missing_rows_csv must include an 'Item Name' column.")

    photo_dir_path = Path(photo_dir)
    if not photo_dir_path.exists():
        raise FileNotFoundError(f"Photo directory not found: {photo_dir}")

    photos_by_name = {}
    for entry in photo_dir_path.iterdir():
        if entry.is_file() and entry.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            photos_by_name[entry.stem.upper()] = entry

    total_rows = len(df)
    successes = 0
    skipped = 0
    failures = []

    for row_index, row in df.iterrows():
        item_name = str(row["Item Name"]).strip()
        short_name = extract_item_number(item_name)
        local_path = photos_by_name.get(short_name.upper())
        if not local_path:
            failures.append((short_name, "missing photo"))
            print(f"[{row_index + 1}/{total_rows}] Missing photo for {short_name}", flush=True)
            continue

        try:
            req = client.catalog.search_catalog_items(body={"text_filter": short_name}).body
            items = req.get("items", [])
        except Exception as exc:
            failures.append((short_name, f"search error: {exc}"))
            print(f"[{row_index + 1}/{total_rows}] Search failed for {short_name}: {exc}", flush=True)
            continue

        if not items:
            failures.append((short_name, "no catalog items found"))
            print(f"[{row_index + 1}/{total_rows}] No catalog items for {short_name}", flush=True)
            continue

        matched_item = None
        for item in items:
            item_short_name = extract_item_number(item["item_data"]["name"])
            if item_short_name == short_name:
                matched_item = item
                break
        if matched_item is None and len(items) == 1:
            matched_item = items[0]

        if matched_item is None:
            failures.append((short_name, "multiple matches"))
            print(f"[{row_index + 1}/{total_rows}] Multiple matches for {short_name}", flush=True)
            continue

        existing_images = matched_item["item_data"].get("image_ids") or []
        if skip_existing and existing_images:
            skipped += 1
            print(f"[{row_index + 1}/{total_rows}] Skipping {short_name}: already has images.", flush=True)
            continue

        try:
            upload_photo_to_square(
                client,
                matched_item["id"],
                short_name,
                matched_item["item_data"]["name"],
                local_path,
                edited=False,
            )
            successes += 1
            print(f"[{row_index + 1}/{total_rows}] Uploaded photo for {short_name}", flush=True)
        except Exception as exc:
            failures.append((short_name, f"upload failed: {exc}"))
            print(f"[{row_index + 1}/{total_rows}] Upload failed for {short_name}: {exc}", flush=True)

    print(
        f"Processed {total_rows} rows. Uploaded {successes} images. "
        f"Skipped {skipped}. Failures: {len(failures)}.",
        flush=True,
    )
    if failures:
        print("Failed uploads:")
        for style, reason in failures:
            print(f"  {style}: {reason}")

def update_missing_items_to_catalog(catalog_path, invoice_path):
    invoice_df = pd.read_csv(invoice_path)
    catalog_df = pd.read_csv(catalog_path)
    # Extract item numbers (will drop at end)
    catalog_df['ItemNumber'] = catalog_df['Item Name'].apply(extract_item_number)

    # Get item names from invoice_df that are missing in subset_df
    missing_items = invoice_df[~invoice_df['Number'].isin(catalog_df['ItemNumber'])]
    # Display or print the missing item names
    print(f"Missing items in subset_df: {len(missing_items)} items")
    # missing_items[['Number', 'SKU', 'FormattedName']].to_string(index=False)
    print(missing_items.to_string(index=False))

    # Create new rows for missing items
    new_catalog_entries = missing_items[['SKU', 'FormattedName']].rename(columns={
        'FormattedName': 'Item Name',
        'SKU': 'SKU'
    })

    # Concatenate the new entries to the existing catalog
    catalog_df = pd.concat([catalog_df, new_catalog_entries], ignore_index=True)

    # Write the full updated catalog back to CSV (drop item number column)
    output_path = catalog_path.replace('.csv', '_MISSING_ADDED.csv')
    catalog_df.to_csv(output_path, index=False)

    print("Catalog updated successfully.")
    return output_path


def process_rm_order(rm_csv_count_path, rm_csv_invoice_path, latest_catalog, rm_fiver_photo_downloaded_path):
    rm_count_formatted = format_rm_inventory_received(rm_csv_count_path)
    rm_invoice_formatted = format_rm_invoice_received(rm_csv_invoice_path)
    compare_path = compare_invoice_count_to_our_count(rm_count_formatted, rm_invoice_formatted)
    missing_added_catalog = update_missing_items_to_catalog(latest_catalog, rm_invoice_formatted)
    output_catalog_updated_path = rename_items_in_catalog(missing_added_catalog, rm_invoice_formatted)
    rename_files_in_directory(os.path.join(rm_fiver_photo_downloaded_path, 'BlankImages'))
    rename_files_in_directory(os.path.join(rm_fiver_photo_downloaded_path, 'EditedImages'))


if __name__ == '__main__':
    # CSV of PolarX inventory counted
    csv_counted_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'ORNAMENTS_2024.csv')
    # CSV of latest catalog export from square
    latest_catalog = os.path.join(os.path.expanduser('~'), 'Downloads', 'LATEST_CATALOG.csv')
    # CSV of invoice that polarx provides
    invoice_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'polarx_invoice_2.csv')
    # Directory of images to upload
    fiver_photo_downloaded_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'PolarXOrnaments')
    rm_fiver_photo_downloaded_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'Rudolph_And_Me')
    # CSV of RM Ornaments
    rm_csv_invoice_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'rudolph-and-me-invoice.csv')
    # CSV of RM inventory counted
    rm_csv_count_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'rudolph-and-me-count.csv')

    # # CSV of output of csv_counted_path formatted
    # output_path_inventory_counted = csv_counted_path.replace('.csv', '_OUTPUT.csv')
    #
    # # format our inventory recorded file
    # output_formatted_inventory_path = format_inventory_received(csv_counted_path, output_path_inventory_counted)
    #
    # # format our invoice file
    # output_formatted_invoice_path = format_invoice_received(invoice_path)
    #
    # # compare_invoice_count_to_our_count(output_path, invoice_path)
    # compare_path = compare_invoice_count_to_our_count(output_formatted_inventory_path, output_formatted_invoice_path)
    #
    # # update catalog with the counts here, catalog, description, etc.
    # missing_added_catalog = update_missing_items_to_catalog(latest_catalog, output_formatted_invoice_path)
    # output_catalog_updated_path = rename_items_in_catalog(missing_added_catalog, output_formatted_invoice_path)
    #
    # # get the list of photos missing (checks both blank and edited images)
    # missing_photo_ids = find_missing_photos(fiver_photo_downloaded_path, output_formatted_invoice_path)

    # handle end to end rudolph and me processing
    # process_rm_order(rm_csv_count_path, rm_csv_invoice_path, latest_catalog, rm_fiver_photo_downloaded_path)


    token = 'EAAAEKHmcTf8lNpjSZikvGee86RQxsWTfZxRXjxmKILSee6GeRmRXtR8KlzBvqnm'
    client = get_square_client(token)

    # get_all_catalog_items(client)
    # missing_items = get_all_catalog_items_missing_images(client)

    # update the images from the folders to the items
    update_photos_of_items(client, os.path.join(fiver_photo_downloaded_path, 'BlankImages'))
    update_photos_of_items(client, os.path.join(fiver_photo_downloaded_path, 'EditedImages'), edited=True)



# curl https://connect.squareup.com/v2/catalog/images \
#   -X POST \
#   -H 'Square-Version: 2022-10-19' \
#   -H 'Authorization: Bearer '' \
#   -H 'Accept: application/json' \
#   -F 'file=@/Users/ahaidrey/Downloads/Ornaments2022/OR2026-4.jpg' \
#   -F 'request={
#     "idempotency_key": "OR2026-4",
#     "object_id": "NUY2THAJA53PAD62FMCIQTJK",
#     "image": {
#       "id": "#OR2026-4",
#       "type": "IMAGE",
#       "image_data": {
#         "caption": "FAMILY SERIES - FARM HOUSE FAMILY OF 4 (OR2026-4)"
#       }
#     }
#   }'
