const fs = require('fs');
const path = require('path');

function formatDate(date, pattern) {
  const pad = (num) => String(num).padStart(2, '0');
  if (pattern === 'yyyy-MM-dd') {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }
  if (pattern === 'HH:mm:ss') {
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }
  throw new Error(`Unsupported format: ${pattern}`);
}

function extractOrderDetailsFromHtml(htmlBody, emailDate) {
  const details = {};
  const normalizedHtml = htmlBody.replace(/&nbsp;/gi, ' ');

  function findTextBetween(text, startString, endString) {
    const startIndex = text.indexOf(startString);
    if (startIndex === -1) return null;
    const subString = text.substring(startIndex + startString.length);
    const endIndex = subString.indexOf(endString);
    if (endIndex === -1) return null;
    return subString.substring(0, endIndex).trim();
  }

  let match = htmlBody.match(/<span class="order-transmission__header-shop-name"[^>]*>([^<]+)<\/span>/);
  if (match && match[1]) {
    details['restaurant_name'] = match[1].trim().replace(/&amp;/g, '&');
  }

  match = htmlBody.match(/Order: (\d+)/);
  if (match && match[1]) {
    details['order_number'] = match[1].trim();
  } else {
    match = htmlBody.match(/<strong>Order: <span class="order-transmission__blue"[^>]*>(\d+)<\/span><\/strong>/);
    if (match && match[1]) {
      details['order_number'] = match[1].trim();
    }
  }

  match = htmlBody.match(/(\w+), (\w+ \d+) at (\d+:\d+ (?:AM|PM))/);
  if (match) {
    details['day_of_week'] = match[1];
    const orderMonthDay = match[2];
    const orderTimeStr = match[3];

    let year = emailDate.getFullYear();
    const emailMonth = emailDate.getMonth();
    const orderMonth = new Date(Date.parse(orderMonthDay.split(' ')[0] + ' 1, 2000')).getMonth();

    if (emailMonth === 0 && orderMonth === 11) {
      year -= 1;
    }

    const dateStr = `${orderMonthDay}, ${year} ${orderTimeStr}`;
    try {
      const dtObject = new Date(dateStr);
      details['order_date'] = formatDate(dtObject, 'yyyy-MM-dd');
      details['order_time'] = formatDate(dtObject, 'HH:mm:ss');
    } catch (e) {
      console.log(`Error parsing date: ${dateStr} - ${e}`);
      details['order_date'] = null;
      details['order_time'] = null;
    }
  }

  let customerInfoTdMatch = htmlBody.match(/<td class="order-transmission__meta-double[^>]*>([\s\S]*?)<\/td>/);
  if (customerInfoTdMatch && customerInfoTdMatch[1]) {
    const customerInfoHtml = customerInfoTdMatch[1];

    match = customerInfoHtml.match(/<strong>([^<]+)<\/strong>/);
    if (match && match[1]) {
      const nameParts = match[1].trim().split(' ');
      if (nameParts.length > 0 && !nameParts[0].includes('Instructions')) {
        details['first_name'] = nameParts[0];
        details['last_name'] = nameParts.length > 1 ? nameParts[1] : '';
      }
    }

    match = customerInfoHtml.match(/<a href="tel:(\d+)"[^>]*>(\d+)<\/a>/);
    if (match && match[2]) {
      details['phone_number'] = match[2].trim();
    } else {
      match = customerInfoHtml.match(/(\d{10})/);
      if (match && match[1]) {
        details['phone_number'] = match[1].trim();
      }
    }

    let namePhoneTableMatch = customerInfoHtml.match(/(<table[^>]*class="row"[^>]*>[\s\S]*?<strong>[^<]+<\/strong>[\s\S]*?<a href="tel:\d+"[^>]*>\d+<\/a>[\s\S]*?<\/table>)/);
    if (namePhoneTableMatch && namePhoneTableMatch[1]) {
      const namePhoneTableHtml = namePhoneTableMatch[1];
      const afterNamePhoneTable = customerInfoHtml.split(namePhoneTableHtml)[1];
      if (afterNamePhoneTable) {
        let addressTableMatch = afterNamePhoneTable.match(/(<table[^>]*class="row"[^>]*>[\s\S]*?<\/table>)/);
        if (addressTableMatch && addressTableMatch[1]) {
          const addressTableHtml = addressTableMatch[1];
          const addressLinesRaw = addressTableHtml
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<[^>]+>/g, '\n')
            .replace(/&nbsp;/gi, ' ')
            .split(/\n+/)
            .map(line => line.trim())
            .filter(line => line !== '');
          if (addressLinesRaw.length > 0 && addressLinesRaw[0].toUpperCase() !== 'PICKUP') {
            const cleanedLines = addressLinesRaw.map(line => line.replace(/,\s*$/, '').trim());
            details['address'] = cleanedLines.join(', ');
          }
        }
      }
    }
  }

  function extractPrice(label) {
    const baseLabel = label.replace(/:\s*$/, '');
    const escapedLabel = baseLabel.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');
    const labelRegex = new RegExp(String.raw`${escapedLabel}\s*:`, 'i');
    const labelMatch = labelRegex.exec(normalizedHtml);
    if (!labelMatch) {
      return null;
    }
    const searchArea = normalizedHtml.slice(labelMatch.index + labelMatch[0].length);
    let priceMatch = searchArea.match(/<td[^>]*>\s*(\$[\d\.,]+)\s*<\/td>/i);
    if (priceMatch && priceMatch[1]) {
      return priceMatch[1].trim();
    }
    priceMatch = searchArea.match(/<p[^>]*>\s*(\$[\d\.,]+)\s*<\/p>/i);
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

  match = normalizedHtml.match(/Discount Percent\s*:[\s\S]*?<p[^>]*>\s*(-?\$?[\d\.,]+%?)\s*<\/p>/i);
  if (match && match[1]) {
    details['discount_percent'] = match[1].trim();
  } else {
    details['discount_percent'] = null;
  }

  let totalMatch = normalizedHtml.match(/Total[\s\S]*?<strong[^>]*>\s*(\$[\d\.,]+)\s*<\/strong>/i);
  if (totalMatch && totalMatch[1]) {
    details['total'] = totalMatch[1].trim();
  } else {
    details['total'] = extractPrice('Total');
  }

  match = normalizedHtml.match(/<span class="order-transmission__meta-desc"[^>]*>\s*(CREDIT|CASH)\s*<\/span>/i);
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

function main() {
  const htmlPath = path.join(__dirname, 'sample_record.html');
  const htmlBody = fs.readFileSync(htmlPath, 'utf8');
  const emailDate = new Date('2025-10-15T12:00:00');
  const details = extractOrderDetailsFromHtml(htmlBody, emailDate);
  console.log(details);
}

if (require.main === module) {
  main();
}

module.exports = { extractOrderDetailsFromHtml };
