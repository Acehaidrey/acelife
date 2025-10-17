// const orderLabel = 'Orders';
// const Platform = {
//   GRUBHUB: 'Grubhub',
// };

const GRUBHUB_SPREADSHEET_ID = '1bnwEN-yY-ton6VLbAxyuu13LeAUzUAF9G_G6KCQ5Mro'; // '1qsSrlrVyyV9KbFpJOrBtOPKbSZoGhussHoV5iJoNXls'; // Provided Spreadsheet ID

const GRUBHUB_SHEET_NAME = 'Grubhub Order History';
const GRUBHUB_HEADERS = [
  'Restaurant', 'Date', 'Order Number', 'Customer Name', 'Phone Number',
  'Email', 'Address', 'Del Fee', 'Tip', 'Tax', 'Subtotal', 'Total'
];

const GRUBHUB_DEBUG_HTML_SHEET_NAME = 'Grubhub Debug HTML';

function logGrubhubHtmlToSheet(htmlContent, orderNumber) {
  const spreadsheet = SpreadsheetApp.openById(GRUBHUB_SPREADSHEET_ID);
  let debugSheet = spreadsheet.getSheetByName(GRUBHUB_DEBUG_HTML_SHEET_NAME);

  if (!debugSheet) {
    debugSheet = spreadsheet.insertSheet(GRUBHUB_DEBUG_HTML_SHEET_NAME);
    debugSheet.appendRow(['Order Number', 'Full HTML Content']);
  }

  debugSheet.appendRow([orderNumber, htmlContent]);
  Logger.log(`Full HTML for order ${orderNumber} logged to sheet "${GRUBHUB_DEBUG_HTML_SHEET_NAME}".`);
}

function extractGrubhubOrdersForYesterday() {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  extractGrubhubOrdersToGoogleSheet(yesterday, today);
}

function extractGrubhubOrdersToGoogleSheet(startDateInput, endDateInput) {
  const userLabel = `${orderLabel}/${Platform.GRUBHUB}`;
  const label = GmailApp.getUserLabelByName(userLabel);

  if (!label) {
    Logger.log(`ERROR: Label "${userLabel}" not found.`);
    return;
  }

  const { startDate, endDate, query } = buildThreadQuery(userLabel, startDateInput, endDateInput);
  let threads;

  if (query) {
    threads = GmailApp.search(query);
    Logger.log(`Processing ${threads.length} email threads for ${userLabel} using query: ${query}`);
  } else {
    threads = label.getThreads();
    Logger.log(`Processing ${threads.length} email threads for ${userLabel}.`);
  }

  const spreadsheet = SpreadsheetApp.openById(GRUBHUB_SPREADSHEET_ID);
  const sheet = spreadsheet.getSheetByName(GRUBHUB_SHEET_NAME);

  if (!sheet) {
    Logger.log(`ERROR: Sheet "${GRUBHUB_SHEET_NAME}" not found in spreadsheet ID "${GRUBHUB_SPREADSHEET_ID}".`);
    return;
  }

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(GRUBHUB_HEADERS);
  }

  for (let i = 0; i < threads.length; i++) {
    const thread = threads[i];
    const messages = thread.getMessages();
    if (!messages || messages.length === 0) {
      continue;
    }

    const message = messages[0];
    const htmlBody = message.getBody();
    const emailDate = message.getDate();

    if (startDate && emailDate < startDate) {
      continue;
    }
    if (endDate && emailDate > endDate) {
      continue;
    }

    const orderDetails = extractGrubhubOrderDetailsFromHtml(htmlBody, emailDate);

    if (orderDetails && orderDetails['order_number']) {
      const customerName = orderDetails['customer_name'] || '';
      const rowData = [
        orderDetails['restaurant_name'] || '',
        orderDetails['order_datetime'] || orderDetails['order_date'] || '',
        orderDetails['order_number'] || '',
        customerName || '',
        orderDetails['phone_number'] || '',
        orderDetails['email'] || '',
        orderDetails['address'] || '',
        orderDetails['delivery_fee'] || '',
        orderDetails['tip'] || '',
        orderDetails['tax'] || '',
        orderDetails['subtotal'] || '',
        orderDetails['total'] || ''
      ];
      sheet.appendRow(rowData);
      message.markRead();
    } else {
      const orderNum = orderDetails && orderDetails['order_number'] ? orderDetails['order_number'] : 'UNKNOWN_ORDER';
      logGrubhubHtmlToSheet(htmlBody, orderNum);
      Logger.log(`No valid Grubhub order details extracted. Full HTML logged for ${orderNum}.`);
    }
  }

  Logger.log(`Finished processing emails for ${userLabel}.`);
}

function extractGrubhubOrderDetailsFromHtml(htmlBody, emailDate) {
  const details = {};
  const normalizedHtml = htmlBody.replace(/&nbsp;/gi, ' ');

  function cleanText(text) {
    if (!text) return '';
    return text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function getDataField(fieldName) {
    const regex = new RegExp(`<div[^>]+data-field="${fieldName}"[^>]*>([\\s\\S]*?)<\\/div>`, 'i');
    const match = normalizedHtml.match(regex);
    return match ? cleanText(match[1]) : null;
  }

  const restaurantName = getDataField('restaurant-name');
  if (restaurantName) {
    details['restaurant_name'] = standardizeRestaurantName(restaurantName);
  }

  const scheduledRaw = getDataField('scheduled-dt');
  if (scheduledRaw) {
    const cleanedSchedule = scheduledRaw.replace(/\s+/g, ' ').trim();
    let parsedDate = new Date(cleanedSchedule);

    if (isNaN(parsedDate.getTime())) {
      const scheduleMatch = cleanedSchedule.match(/([A-Za-z]+),?\s+([A-Za-z]+ \d{1,2})(?:,)?\s*(\d{4})?\s*(?:at)?\s*(\d+:\d+\s*(?:AM|PM))/i);
      if (scheduleMatch) {
        const dayName = scheduleMatch[1];
        const monthDay = scheduleMatch[2];
        const year = scheduleMatch[3] ? scheduleMatch[3] : String(emailDate.getFullYear());
        const timeStr = scheduleMatch[4];
        parsedDate = new Date(`${monthDay}, ${year} ${timeStr}`);
        if (!isNaN(parsedDate.getTime())) {
          details['day_of_week'] = dayName;
        }
      }
    }

    if (!isNaN(parsedDate.getTime())) {
      const timezone = Session.getScriptTimeZone();
      details['order_date'] = Utilities.formatDate(parsedDate, timezone, 'yyyy-MM-dd');
      details['order_time'] = Utilities.formatDate(parsedDate, timezone, 'HH:mm:ss');
      details['order_datetime'] = Utilities.formatDate(parsedDate, timezone, 'yyyy-MM-dd HH:mm:ss');
      if (!details['day_of_week']) {
        details['day_of_week'] = Utilities.formatDate(parsedDate, timezone, 'EEEE');
      }
    }
  } else if (emailDate) {
    const timezone = Session.getScriptTimeZone();
    details['order_date'] = Utilities.formatDate(emailDate, timezone, 'yyyy-MM-dd');
    details['order_time'] = Utilities.formatDate(emailDate, timezone, 'HH:mm:ss');
    details['order_datetime'] = Utilities.formatDate(emailDate, timezone, 'yyyy-MM-dd HH:mm:ss');
    details['day_of_week'] = Utilities.formatDate(emailDate, timezone, 'EEEE');
  }

  const phoneNumber = getDataField('phone');
  if (phoneNumber) {
    const digitsOnly = phoneNumber.replace(/[^\d]/g, '');
    details['phone_number'] = digitsOnly.length >= 10 ? digitsOnly.slice(-10) : digitsOnly;
  }

  const address1 = getDataField('address1');
  const address2 = getDataField('address2');
  const city = getDataField('city');
  const state = getDataField('state');
  const zip = getDataField('zip');
  const addressParts = [address1, address2, city, state, zip].filter(Boolean);
  if (addressParts.length > 0) {
    const formatted = addressParts.join(', ').replace(/\s+,/g, ',').replace(/,,+/g, ',');
    details['address'] = formatted;
  }

  function assignPriceField(fieldName, targetKey) {
    const value = getDataField(fieldName);
    if (value && value !== 'N/A') {
      details[targetKey] = value;
    }
  }

  assignPriceField('subtotal', 'subtotal');
  assignPriceField('sales-tax', 'tax');
  assignPriceField('tip', 'tip');
  assignPriceField('delivery-charge', 'delivery_fee');
  assignPriceField('total', 'total');

  const orderNumberMatch = normalizedHtml.match(/Order:\s*<strong>#([\d\s—-]+)<\/strong>/i);
  if (orderNumberMatch) {
    details['order_number'] = cleanText(orderNumberMatch[1]).replace(/\s+/g, ' ');
  }

  function extractCustomerName(labelText) {
    const labelRegex = new RegExp(`${labelText}\\s*</div>\\s*<div[^>]*>([\\s\\S]*?)<\\/div>`, 'i');
    const match = normalizedHtml.match(labelRegex);
    return match ? cleanText(match[1]) : null;
  }

  let customerName = extractCustomerName('Deliver to:');
  if (!customerName) {
    customerName = extractCustomerName('Pickup by:');
  }

  if (customerName) {
    details['customer_name'] = customerName;
  }

  const emailMatch = normalizedHtml.match(/mailto:([^"?\s]+)"/i);
  if (emailMatch) {
    details['email'] = emailMatch[1].trim();
  }

  return details;
}

function standardizeRestaurantName(name) {
  if (!name) return name;
  const trimmedName = name.trim();
  const lowerName = trimmedName.toLowerCase();
  if (lowerName.includes('aroma')) {
    return 'Aroma';
  }
  if (lowerName.includes('ameci')) {
    return 'Ameci';
  }
  if (lowerName.includes('wing')) {
    return 'Wingstop';
  }
  if (lowerName.includes('trattoria contadina')) {
    return 'Trattoria Contadina';
  }
  return trimmedName;
}
