const utils = require("./utils");
const {TransactionRecord} = require("./record");
const {Platform, paymentType, errorType} = require("./constants");
const { JSDOM } = require('jsdom');

const regexStoreName = /(Aroma|Ameci)/i;
const regexOrderId = /Order (.*) Confirmation/i;
const regexCustomerName = /(Pickup by|Deliver to):\s+([A-Za-z\-]+(?:\s+[A-Za-z]+)*\s+[A-Za-z.\-]+\s*\b)/;
const regexAddress = /^(.*?), \((\d{3})\)\s*\d{3}-\d{4}/s;
const regexCityStZip = /^(.*),\s*([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})$/;


function createTransactionRecord(mail) {
    const record = new TransactionRecord(Platform.GRUBHUB, mail.date);
    const { window } = new JSDOM(mail.html);
    const doc = window.document;

    const divEls = doc.querySelectorAll('div[data-field]');
    divEls.forEach((divEl) => {
      const dataFieldValue = divEl.getAttribute('data-field');
      const divTextContent = divEl.textContent;
      // Get phone number
      if (dataFieldValue === 'phone') {
          record.customerNumber = utils.formatPhoneNumber(divTextContent);
      }
      // Get order type
      if (dataFieldValue === 'service-type') {
          record.orderType = utils.formatString(divTextContent).toUpperCase();
      }
      // Get order amount
      if (dataFieldValue === 'total') {
          record.orderAmount = parseFloat(utils.formatString(divTextContent.replace('$', '')));
      }
      // Get store name
      if (dataFieldValue === 'restaurant-name') {
        const storeNameMatch = divTextContent.match(regexStoreName);
        if (storeNameMatch) {
            record.storeName = utils.formatString(storeNameMatch[1].toUpperCase());
        } else {
            record.storeName = utils.formatString(divTextContent);
            swapVRStoreName(record);
        }
      }
      // Get payment type
      if (dataFieldValue === 'payment-is-cash') {
          record.paymentType = divTextContent.toLowerCase().trim() === 'true' ? paymentType.CASH : paymentType.CREDIT;
      }
    });
    // Get order ID
    const orderIdMatch = mail.subject.match(regexOrderId);
    if (orderIdMatch) {
        record.orderId = utils.formatString(orderIdMatch[1]);
    }

    let customerInfo = doc.getElementsByClassName("pickup-delivery-box");
    if (customerInfo && customerInfo.length >= 1) {
        customerInfo = customerInfo[0].textContent;
        // Get customer name
        const customerNameMatch = customerInfo.match(regexCustomerName);
        if (customerNameMatch) {
            record.customerName = utils.formatString(customerNameMatch[2].toUpperCase());
        }
        // Get customer address if self delivery
        if (mail.html.toLowerCase().includes("self delivery")) {
            const address = utils.formatString(customerInfo.replace(/\s{4}/g, ','))
                .toUpperCase()
                .replace('DELIVER TO:', '').trim()
                .replace(record.customerName, '').trim()
                .replace(/,{2,}/g, ',').trim()
                .replace(/^,*(.*?),*$/, '$1').trim();
            const addressMatch = address.match(regexAddress);
            if (addressMatch) {
                record.customerAddress = utils.formatString(addressMatch[1]);
                const stCityStZipMatch = record.customerAddress.match(regexCityStZip);
                if (stCityStZipMatch) {
                    record.street = stCityStZipMatch[1];
                    record.city = stCityStZipMatch[2];
                    record.state = stCityStZipMatch[3];
                    record.zipcode = parseInt(stCityStZipMatch[4]);
                } else {
                    utils.recordError(record, errorType.STREET);
                    utils.recordError(record, errorType.CITY);
                    utils.recordError(record, errorType.STATE);
                    utils.recordError(record, errorType.ZIPCODE);
                }
            } else {
                utils.recordError(record, errorType.CUSTOMER_ADDRESS);
            }
        }
    } else {
        utils.recordError(record, 'customerInfo element does not exist');
    }
    // If any of the above fields are null then set record error
    setErrorMessageForMissingFields(record);
    if (record.error) {
        record.mail = mail.html;
    }
    return record;
}

/**
 * Checks if any of the given parameters are null and then sets a respective error message.
 * @param {TransactionRecord} record
 */
function setErrorMessageForMissingFields(record) {
    if (!record.storeName) {
        utils.recordError(record, errorType.STORE_NAME);
    }
    if (!record.orderType) {
        utils.recordError(record, errorType.ORDER_TYPE);
    }
    if (!record.orderAmount) {
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
}

/**
 * Aroma has virtual restaurants that should just be setting the sales and customers to Aroma.
 * @param {TransactionRecord} record
 */
function swapVRStoreName(record) {
    const VRStores = ['Trattoria Contadina', 'The Wing Shop', 'The Wing Stop'];
    if (VRStores.includes(record.storeName)) {
        record.storeVRName = record.storeName;
        record.storeName = 'AROMA';
    }
}

function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords.filter(function(record) { return !record.error;}));
}

module.exports = {createTransactionRecord, createCustomerRecords}