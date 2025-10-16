// const orderLabel = 'Orders';
// const Platform = {
//   SLICE: 'Slice',
//   // Add other platforms if needed for context, but only Slice is processed here
// };

const SPREADSHEET_ID = '1qsSrlrVyyV9KbFpJOrBtOPKbSZoGhussHoV5iJoNXls'; // Provided Spreadsheet ID
const SHEET_NAME = 'Testing'; // Assuming default sheet name, adjust if needed
const HEADERS = [
  'restaurant_name', 'order_number', 'day_of_week', 'order_date', 'order_time',
  'first_name', 'last_name', 'phone_number', 'address', 'subtotal', 'tax',
  'tip', 'delivery_fee', 'coupon_discount', 'discount_percent', 'total',
  'payment_method', 'last_4_digits'
];

const DEBUG_HTML_SHEET_NAME = 'Debug HTML';

function logFullHtmlToSheet(htmlContent, orderNumber) {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let debugSheet = spreadsheet.getSheetByName(DEBUG_HTML_SHEET_NAME);

  if (!debugSheet) {
    debugSheet = spreadsheet.insertSheet(DEBUG_HTML_SHEET_NAME);
    debugSheet.appendRow(['Order Number', 'Full HTML Content']);
  }

  debugSheet.appendRow([orderNumber, htmlContent]);
  Logger.log(`Full HTML for order ${orderNumber} logged to sheet "${DEBUG_HTML_SHEET_NAME}".`);
}

/**
 * Main function to process Slice order emails, extract details, and save to a Google Sheet.
 */
function extractSliceOrdersToNewSheet() {
  const userLabel = `${orderLabel}/${Platform.SLICE}`;
  const label = GmailApp.getUserLabelByName(userLabel);

  if (!label) {
    Logger.log(`ERROR: Label "${userLabel}" not found.`);
    return;
  }

  const threads = label.getThreads();
  Logger.log(`Processing ${threads.length} email threads for ${userLabel}.`);

  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = spreadsheet.getSheetByName(SHEET_NAME);

  if (!sheet) {
    Logger.log(`ERROR: Sheet "${SHEET_NAME}" not found in spreadsheet ID "${SPREADSHEET_ID}".`);
    return;
  }

  // Add headers if the sheet is empty
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
  }

  for (let i = 0; i < threads.length; i++) {
    const thread = threads[i];
    const messages = thread.getMessages();

    for (let j = 0; j < messages.length; j++) {
      const message = messages[j];
      // Process all messages, regardless of read status
      // if (!message.isUnread()) {
      //   continue;
      // }

      const htmlBody = message.getBody();
      const emailDate = message.getDate(); // Get the date for potential 2019 layout handling

      const orderDetails = extractOrderDetailsFromHtml(htmlBody, emailDate);

      if (orderDetails && orderDetails['order_number']) { // Only save if an order number was extracted
        const rowData = HEADERS.map(header => orderDetails[header] || '');
        sheet.appendRow(rowData);
        message.markRead(); // Mark as read after processing
      } else {
        // Log full HTML to a debug sheet if extraction fails
        const orderNum = orderDetails && orderDetails['order_number'] ? orderDetails['order_number'] : 'UNKNOWN_ORDER';
        logFullHtmlToSheet(htmlBody, orderNum);
        Logger.log(`No valid order details extracted for this message. Full HTML logged for ${orderNum}.`);
      }
    }
    // thread.moveToArchive(); // Archive the thread after processing all messages
  }
  Logger.log(`Finished processing emails for ${userLabel}.`);
}

/**
 * Extracts order details from the HTML body of an email.
 * This function uses regex and string manipulation as a full HTML parser is not available.
 * It attempts to handle both modern and and 2019 layouts.
 */
function extractOrderDetailsFromHtml(htmlBody, emailDate) {
  const details = {};

  // Helper to find text between two strings (inclusive of start, exclusive of end)
  function findTextBetween(text, startString, endString) {
    const startIndex = text.indexOf(startString);
    if (startIndex === -1) return null;
    const subString = text.substring(startIndex + startString.length);
    const endIndex = subString.indexOf(endString);
    if (endIndex === -1) return null;
    return subString.substring(0, endIndex).trim();
  }

  // --- Common Extractions (should work for both layouts if patterns are consistent) ---

  // Restaurant Name
  let match = htmlBody.match(/<span class="order-transmission__header-shop-name"[^>]*>([^<]+)<\/span>/);
  if (match && match[1]) {
    details['restaurant_name'] = match[1].trim().replace(/&amp;/g, '&');
  }

  // Order Number
  // Try modern layout pattern first
  match = htmlBody.match(/Order: (\d+)/);
  if (match && match[1]) {
    details['order_number'] = match[1].trim();
  } else {
    // Try 2019 layout pattern
    match = htmlBody.match(/<strong>Order: <span class="order-transmission__blue"[^>]*>(\d+)<\/span><\/strong>/);
    if (match && match[1]) {
      details['order_number'] = match[1].trim();
    }
  }

  // Order Date, Day of Week, Order Time
  match = htmlBody.match(/(\w+), (\w+ \d+) at (\d+:\d+ (?:AM|PM))/);
  if (match) {
    details['day_of_week'] = match[1];
    const orderMonthDay = match[2];
    const orderTimeStr = match[3];

    let year = emailDate.getFullYear();
    // Basic logic to handle year rollover (e.g., email from Jan, order from Dec last year)
    const emailMonth = emailDate.getMonth(); // 0-11
    const orderMonth = new Date(Date.parse(orderMonthDay.split(' ')[0] + ' 1, 2000')).getMonth(); // Get month index from string

    if (emailMonth === 0 && orderMonth === 11) { // If email is Jan and order is Dec
      year -= 1;
    }

    const dateStr = `${orderMonthDay}, ${year} ${orderTimeStr}`;
    try {
      const dtObject = new Date(dateStr);
      details['order_date'] = Utilities.formatDate(dtObject, Session.getScriptTimeZone(), 'yyyy-MM-dd');
      details['order_time'] = Utilities.formatDate(dtObject, Session.getScriptTimeZone(), 'HH:mm:ss');
    } catch (e) {
      Logger.log(`Error parsing date: ${dateStr} - ${e}`);
      details['order_date'] = null;
      details['order_time'] = null;
    }
  }

  // --- Customer Information (Name, Phone, Address) ---
  // This part is layout-dependent. We'll try to detect the layout.

  // Modern Layout Detection (based on class 'order-transmission__meta-double')
  let customerInfoTdMatch = htmlBody.match(/<td class="order-transmission__meta-double[^>]*>([\s\S]*?)<\/td>/);
  if (customerInfoTdMatch && customerInfoTdMatch[1]) {
    const customerInfoHtml = customerInfoTdMatch[1];

    // Name
    match = customerInfoHtml.match(/<strong>([^<]+)<\/strong>/);
    if (match && match[1]) {
      const nameParts = match[1].trim().split(' ');
      if (nameParts.length > 0 && !nameParts[0].includes("Instructions")) {
        details['first_name'] = nameParts[0];
        details['last_name'] = nameParts.length > 1 ? nameParts[1] : '';
      }
    }

    // Phone Number
    match = customerInfoHtml.match(/<a href="tel:(\d+)"[^>]*>(\d+)<\/a>/);
    if (match && match[2]) {
      details['phone_number'] = match[2].trim();
    } else {
      // Fallback for phone number if not in <a> tag, look for 10 digits in the text directly
      match = customerInfoHtml.match(/(\d{10})/);
      if (match && match[1]) {
        details['phone_number'] = match[1].trim();
      }
    }

    // Address (Modern Layout)
    // Find the table containing the name and phone number
    let namePhoneTableMatch = customerInfoHtml.match(/(<table[^>]*class="row"[^>]*>[\s\S]*?<strong>[^<]+<\/strong>[\s\S]*?<a href="tel:\d+"[^>]*>\d+<\/a>[\s\S]*?<\/table>)/);
    if (namePhoneTableMatch && namePhoneTableMatch[1]) {
      const namePhoneTableHtml = namePhoneTableMatch[1];
      // Now find the next table after this one, which should contain the address
      const afterNamePhoneTable = customerInfoHtml.split(namePhoneTableHtml)[1];
      if (afterNamePhoneTable) {
        let addressTableMatch = afterNamePhoneTable.match(/(<table[^>]*class="row"[^>]*>[\s\S]*?<\/table>)/);
        if (addressTableMatch && addressTableMatch[1]) {
          const addressTableHtml = addressTableMatch[1];
          const addressLinesRaw = addressTableHtml.split(/<br\s*\/?>/).map(line => line.trim()).filter(line => line !== '');
          if (addressLinesRaw.length > 0 && addressLinesRaw[0] !== 'PICKUP') {
            details['address'] = addressLinesRaw.join(', ');
          }
        }
      }
    }

  }

  // --- Price Extractions (Subtotal, Tax, Tip, Delivery Fee, Coupon Discount, Total) ---
  function extractPrice(label) {
    // Look for price in <td> tag first
    let priceMatch = htmlBody.match(new RegExp(`${label}[\s\S]*?<td[^>]*>\s*(\$[\d\.,]+)\s*<\/td>`));
    if (priceMatch && priceMatch[1]) {
      return priceMatch[1].trim();
    }
    // Fallback for <p> tag if <td> not found
    priceMatch = htmlBody.match(new RegExp(`${label}[\s\S]*?<p[^>]*>\s*(\$[\d\.,]+)\s*<\/p>`));
    if (priceMatch && priceMatch[1]) {
      return priceMatch[1].trim();
    }
    return null;
  }

  details['subtotal'] = extractPrice('Subtotal:');
  details['tax'] = extractPrice('Tax:');
  details['tip'] = extractPrice('Tip:');
  details['delivery_fee'] = extractPrice('Delivery Fee:');
  details['coupon_discount'] = extractPrice('Coupon Discount:');

  // Discount Percent is tricky, might need a different pattern
  // For now, let's try to extract it if it's explicitly labeled.
  match = htmlBody.match(/Discount Percent:[\s\S]*?<p[^>]*>\s*(-?\$?[\d\.,]+%?)\s*<\/p>/);
  if (match && match[1]) {
    details['discount_percent'] = match[1].trim();
  } else {
    details['discount_percent'] = null; // Placeholder
  }

  // Total (can be in strong tag or regular price)
  let totalMatch = htmlBody.match(/Total[\s\S]*?<strong>\s*(\$[\d\.,]+)\s*<\/strong>/);
  if (totalMatch && totalMatch[1]) {
    details['total'] = totalMatch[1].trim();
  } else {
    details['total'] = extractPrice('Total');
  }

  // Payment Method and Last 4 Digits
  match = htmlBody.match(/<span class="order-transmission__meta-desc"[^>]*>(CREDIT|CASH)<\/span>/);
  if (match && match[1]) {
    details['payment_method'] = match[1].trim();
    if (details['payment_method'] === 'CREDIT') {
      match = htmlBody.match(/ending in (\d{4})/);
      if (match && match[1]) {
        details['last_4_digits'] = match[1].trim();
      }
    }
  }

  return details;
}
