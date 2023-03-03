const { JSDOM } = require('jsdom');

const utils = require("./utils");
const {CustomerRecord, TransactionRecord} = require("./record");
const {Platform, storeType, errorType, paymentType, orderType} = require("./constants");

const argv = require('yargs')
	.alias('i', 'input')
  .alias('e', 'extra-file')
	.argv;


const OnlineOrderPrefix = 'Online Order #'.toLowerCase();
const DeliveryOrderPrefix = 'New delivery order from:'.toLowerCase();
const regexCityStateZip = /(.*),\s*([A-Za-z]{2})\s*(\d{5})?(?:-(\d{4}))?$/i;

function createTransactionRecord(mail) {
  const isOnlineOrder = mail.subject.toLowerCase().startsWith(OnlineOrderPrefix);
  const isDeliveryOrder = mail.subject.toLowerCase().startsWith(DeliveryOrderPrefix);
  const transRecord = new TransactionRecord(Platform.TOAST, mail.date);
  transRecord.storeName = storeType.AROMA;
  if (!isOnlineOrder && !isDeliveryOrder) {
    utils.recordError(transRecord, errorType.NOT_TRANSACTION_EMAIL);
    return transRecord;
  }
  // payment type -- if payment id exists that means already paid
  transRecord.paymentType = mail.html.includes('Payment ID') ? paymentType.CREDIT : paymentType.CASH;
  // order id (if online order some extra fields set)
  getInfoFromSubject(mail, isDeliveryOrder, isOnlineOrder, transRecord);
  // order type (already set in above call but for online set properly)
  // set customer information
  if (isOnlineOrder) {
    transRecord.orderType = getOrderTypeForOnline(mail.html);
    getCustomerInfoForOnline(mail.html, transRecord);
  }
  // order amount (already set in online order but for delivery need)
  // set customer information
  if (isDeliveryOrder) {
    transRecord.orderAmount = getOrderAmountForDelivery(mail.html);
    getCustomerInfoForDelivery(mail.html, transRecord);
  }
  // mark error records if fields missing
  setErrorMessageForMissingFields(transRecord, isDeliveryOrder, isOnlineOrder);
  return transRecord;
}

/**
 * Parses the email html body to parse the customer info between HR tags and populate the record.
 * @param {string} html 
 * @param {TransactionRecord} record 
 */
function getCustomerInfoForOnline(html, record) {
  const dom = new JSDOM(html);
  const document = dom.window.document;
  const hrTags = document.getElementsByTagName("hr");
  let customerCells = [];
  // from 2nd to 3rd hr tags has all customer information - assume this (can break in future)
  if (hrTags.length > 2) {
    // get outer parent encapsulating the hr which has customer info
    let parentTr = hrTags[1].parentElement.parentElement;
    let nextTr = parentTr.nextElementSibling;
    // loop until we continue to have customer info
    while (nextTr !== null) {
      const cells = Array.from(nextTr.querySelectorAll('td')).map(td => td.textContent.trim());
      customerCells = customerCells.concat(cells);
      nextTr = nextTr.nextElementSibling;
      // if the next element will contain an hr then break out of this
      if (nextTr && nextTr.querySelector('hr') !== null) {
        break;
      }
    }
    customerCells = customerCells.filter(cell => cell !== '' && !cell.startsWith('Notes:'));
    if (customerCells && customerCells.length > 1) {
      record.customerName = utils.formatString(customerCells[0].toUpperCase());
      record.customerEmail = utils.formatString(customerCells[customerCells.length - 1].toUpperCase());
      if (record.orderType === orderType.PICKUP && customerCells.length > 2) {
        // format for pickup orders is [customer name, phone number, email]
        record.customerNumber = utils.formatPhoneNumber(customerCells[1]);
      }
      if (record.orderType === orderType.DELIVERY && customerCells.length > 3) {
        // format for delivery orders is [customer name, street, phone number, (city, state, zip), additional address, email]
        record.customerNumber = utils.formatPhoneNumber(customerCells[2]);
        record.street = utils.formatString(customerCells[1].toUpperCase());
        for (let i = 3; i < customerCells.length - 2; i++) {
          record.street += ' #' + utils.formatString(customerCells[i].toUpperCase().replace('#', ''));
        }
        const matchCityStateZip = customerCells[customerCells.length - 2].match(regexCityStateZip);
        if (matchCityStateZip) {
          record.city = utils.formatString(matchCityStateZip[1].toUpperCase());
          record.state = utils.shortStateName(matchCityStateZip[2]);
          record.zipcode = parseInt(utils.getZipForCity(matchCityStateZip[3], record.city));
        }
        record.customerAddress = utils.createFullAddress(record.street, record.city, record.state, record.zipcode);
      }
    }
  }
}

/**
 * Finds the innermost TR element that contains the customer info.
 * @param {HTMLElement} element 
 * @returns {HTMLTableRowElement}
 */
function getInnermostTrWithCustomerInfo(element) {
  let targetTr = null;
  if (element.tagName === "TR" && /\bCustomer Info\b/.test(element.textContent)) {
    targetTr = element;
  } else {
    for (const childElement of element.children) {
      const innerTr = getInnermostTrWithCustomerInfo(childElement);
      if (innerTr) {
        targetTr = innerTr;
        break;
      }
    }
  }
  return targetTr;
}

/**
 * Parses the email html body for the customer information for delivery email format.
 * @param {string} html 
 * @param {TransactionRecord} record 
 */
function getCustomerInfoForDelivery(html, record) {
  const dom = new JSDOM(html);
  const document = dom.window.document;
  const innermostTr = getInnermostTrWithCustomerInfo(document.documentElement);
  if (innermostTr) {
    // slice 3 because first 3 items have the full string containing the Customer Info and want the string that
    // '<strong>Customer Info</strong>',
    // 'Frank<br> 122 Finch<br>Lake Forest, CA 92630<br> 818-284-2683'
    const tdValues = Array.from(innermostTr.querySelectorAll("td")).map(td => td.innerHTML.trim().replace(/\s+/g, ' ')).slice(3);
    const customerInfoIndex = tdValues.findIndex(str => str.includes('Customer Info'));
    if (customerInfoIndex !== -1 && customerInfoIndex < tdValues.length - 1) {
      let customerInfo = tdValues[customerInfoIndex + 1];
      customerInfo = customerInfo.split('<br>').filter(part => part.trim() !== '');
      record.customerName = utils.createFullName(customerInfo[0], null);
      record.customerNumber = utils.formatPhoneNumber(customerInfo[customerInfo.length - 1]);
      const matchCityStateZip = customerInfo[customerInfo.length - 2].match(regexCityStateZip);
      if (matchCityStateZip) {
        record.city = utils.formatString(matchCityStateZip[1].toUpperCase());
        record.state = utils.shortStateName(matchCityStateZip[2]);
        record.zipcode = parseInt(utils.getZipForCity(matchCityStateZip[3], record.city));
      }
      record.street = utils.formatString(customerInfo[1].toUpperCase());
      for (let i = 2; i < customerInfo.length - 2; i++) {
        record.street += ' #' + utils.formatString(customerInfo[i].toUpperCase().replace('#', ''));
      }
      record.customerAddress = utils.createFullAddress(record.street, record.city, record.state, record.zipcode);
    }
  }
}

/**
 * Parses the email html body to retrieve the total cost. Online order types have this in the email subject
 * but the delivery orders need it parsed from the content.
 * @param {string} html 
 * @returns {float}
 */
function getOrderAmountForDelivery(html) {
  const dom = new JSDOM(html);
  const document = dom.window.document;
  const totalCells = document.querySelectorAll("td");
  for (let i = 0; i < totalCells.length; i++) {
    const text = totalCells[i].textContent;
    if (text.includes("Total")) {
      // Split the string into lines using a regular expression to match one or more spaces
      const lines = text.trim().split(/\s+/);
      // Find the index of the line with "Total"
      const totalIndex = lines.findIndex(line => line === "Total");
      // Get the value after "Total" which contains the true value
      const totalValue = parseFloat(lines[totalIndex + 1].replace("$", ""));
      return totalValue;
    }
  }
  return -1;
}

/**
 * Parses the email html body and parses out the order type between the first and second hr tags
 * for online order types.
 * @param {string} html 
 * @returns {orderType}
 */
function getOrderTypeForOnline(html) {
  const dom = new JSDOM(html);
  const document = dom.window.document;
  // first hr gets the pickup / delivery info
  const hrTag = document.querySelector('hr');
  if (hrTag) {
    // Get the parent <tr> element of the <hr> tag
    const parentTr = hrTag.parentNode.parentNode;
    // Find the <td> cells that contain the customer information
    const customerCells = Array.from(parentTr.nextElementSibling.querySelectorAll('td'));
    if (customerCells.length > 0) {
      const orderTypeString = utils.formatString(customerCells[0].textContent);
      return orderTypeString.match(/Pick Up/i) ? orderType.PICKUP : orderType.DELIVERY;
    }
  }
}

/**
 * Abstract information from the subject header to retrieve customer information.
 * In both cases we get a preliminary name and we get order Id.
 * @param {*} mail 
 * @param {boolean} delOrder 
 * @param {boolean} onlineOrder 
 * @param {TransactionRecord} record 
 */
function getInfoFromSubject(mail, delOrder, onlineOrder, record) {
  const subject = mail.subject;
  if (delOrder) {
    const regexOrderNumber = /#(\d+)/i;
    const regexCustomerName = /for (.+)/i;
    const orderNumberMatch = subject.match(regexOrderNumber);
    const customerNameMatch = subject.match(regexCustomerName);
    record.orderId = orderNumberMatch ? createOrderNumber(mail.date, orderNumberMatch[1]) : null;
    record.customerName = customerNameMatch ? customerNameMatch[1].toUpperCase() : null;
    record.orderType = orderType.DELIVERY;
  }
  if (onlineOrder) {
    const regexOrderNumber = /Order #(\d+)/i;
    const regexTotalAmount = /\$([\d.]+)/;
    const regexCustomerName = /for (\w+)/i;
    const orderNumberMatch = subject.match(regexOrderNumber);
    const totalAmountMatch = subject.match(regexTotalAmount);
    const customerNameMatch = subject.match(regexCustomerName);
    record.orderId = orderNumberMatch ? createOrderNumber(mail.date, orderNumberMatch[1]) : null;
    record.customerName = customerNameMatch ? customerNameMatch[1].toUpperCase() : null;
    record.orderAmount = totalAmountMatch ? parseFloat(totalAmountMatch[1]) : null;
  }
}

/**
 * Create order number based off of the date and check number. This is a unique identifier.
 * @param {Date} date 
 * @param {string|int} checkNumber 
 * @returns {string}
 */
function createOrderNumber(date, checkNumber) {
  return `${utils.formatDate(date)}-${checkNumber}`
}

/**
 * Checks if any of the given parameters are null and then sets a respective error message.
 * @param {TransactionRecord} record
 */
function setErrorMessageForMissingFields(record, isDelEmail, isOnlineEmail) {
  if (!record.orderType) {
      utils.recordError(record, errorType.ORDER_TYPE);
  }
  if ((record.orderAmount < 0 && isDelEmail) || (!record.orderAmount && isOnlineEmail)) {
      utils.recordError(record, errorType.ORDER_AMOUNT);
  }
  if (!record.orderId) {
      utils.recordError(record, errorType.ORDER_ID);
  }
  if (!record.paymentType) {
      utils.recordError(record, errorType.PAYMENT_TYPE);
  }
  if (!record.customerNumber) {
      utils.recordError(record, errorType.CUSTOMER_NUMBER);
  }
  if (!record.customerName) {
      utils.recordError(record, errorType.CUSTOMER_NAME);
  }
  if (isDelEmail || (isOnlineEmail && record.orderType === orderType.DELIVERY)) {
    if (!record.street) {
      utils.recordError(record, errorType.STREET);
    }
    if (!record.city) {
      utils.recordError(record, errorType.CITY);
    }
    if (!record.state) {
      utils.recordError(record, errorType.STATE);
    }
    if (!record.zipcode) {
      utils.recordError(record, errorType.ZIPCODE);
    }
    if (!record.customerAddress) {
      utils.recordError(record, errorType.CUSTOMER_ADDRESS);
    }
  }
  if (record.error) {
    const emailType = isDelEmail ? 'DELIVERY' : 'ONLINE'
    utils.recordError(record, `Email Type: ${emailType}`)
  }
}

/**
 * Parses the customer csv file to create a customer profile. Note this csv misses customer address info.
 * @returns {CustomerRecord[]}
 */
function createCustomerRecordsFromCSV() {
    let customerRecords = [];
    const data = utils.readCSVFile(argv.e);
    data.forEach((record) => {
      // replace the null string representations to real null values
      for (const prop in record) {
        if (record[prop] === '' || record[prop] === 'NULL' || record[prop] === 'N/A') {
            record[prop] = (prop === 'TotalOrderValue' || prop === 'TotalOrders') ? '0' : null;
        } else if (record[prop]) {
            record[prop] = record[prop].trim();
        }
      }
      // setup the new record that will be added - all records besides phone numbers
      const customerRecord = new CustomerRecord(storeType.AROMA, null);
      customerRecord.platforms.add(Platform.TOAST);
      customerRecord.customerNames.add(utils.createFullName(record.firstName, record.lastName));
      customerRecord.orderCount = parseInt(record.totalVisits);
      customerRecord.totalSpend = parseFloat(record.averageSpend) * customerRecord.orderCount;
      customerRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record.lastVisitDate);
      if (record.emails) {
        const emails = record.emails.split(';');
        emails.forEach(email => {
          if (email) {
            customerRecord.customerEmails.add(email.trim());
          }
        });
      }
      // split the phone numbers (can have multiple) and make copies and add a copy of this info for each number
      if (record.phones) {
        const phoneNumbers = record.phones.split(';').filter((val) => val !== '');
        phoneNumbers.forEach(phone => {
          const customerRecordCopy = Object.assign({}, customerRecord);
          customerRecordCopy.customerNumber = utils.formatPhoneNumber(phone.trim());
          customerRecords.push(customerRecordCopy);
        });
      } else {
        if (!utils.customerInformationMissing(customerRecord)) {
          customerRecords.push(customerRecord);
        }
      }
    });
    const originalLength = customerRecords.length;
    customerRecords = utils.mergeCustomerRecordsByPhoneNumber(customerRecords);
    console.log(
      `[TOAST] ${originalLength} original customer records found from csv.\n` +
      `[TOAST] ${customerRecords.length} customer records found after merging from csv.`
    );
    return customerRecords;
}

function createCustomerRecords(transactionRecords) {
  const CSVRecords = createCustomerRecordsFromCSV();
  const transactRecords = utils.aggregateCustomerHistory(transactionRecords.filter(function(record) { return !record.error}));
  let customerRecords = CSVRecords.concat(transactRecords);
  const originalLength = customerRecords.length;
  customerRecords = utils.mergeCustomerRecordsByPhoneNumber(customerRecords);
  console.log(
    `[TOAST] ${transactRecords.length} customer records found from transaction records.\n` +
    `[TOAST] ${originalLength} customer records found from csv records joined with transaction records.\n` +
    `[TOAST] ${customerRecords.length} customer records found after merging phone numbers from csv records with transaction records.`
  );
  return customerRecords;
}

module.exports = {createTransactionRecord, createCustomerRecords}