const utils = require("./utils");
const {TransactionRecord} = require("./record");
const {Platform, errorType, orderType} = require("./constants");

const regexStoreName = /(ameci|aroma)/i;
const regexCustomerName = /Customer Info:\s*<\/span>\s*<br \/>\s*<span.*?>(.*?)<\/span>/;


function createTransactionRecord(mail) {
    const cleanedHtml = utils.formatString(mail.html.replace(/&quot;/g, '"'));
    const record = new TransactionRecord(Platform.EATSTREET, mail.date);
    // Get store name
    const storeNameMatch = cleanedHtml.match(regexStoreName);
    if (storeNameMatch) {
        record.storeName = utils.formatString(storeNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, errorType.STORE_NAME);
	}
    // Get customer name
    const customerNameMatch = cleanedHtml.match(regexCustomerName);
    if (customerNameMatch) {
        record.customerName = utils.formatString(customerNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, errorType.CUSTOMER_NAME);
	}
    // Get address info
    const jsonBody = getOrderJSON(cleanedHtml);
    if (jsonBody) {
        // Get order id
        if (jsonBody.hasOwnProperty('id')) {
            record.orderId = jsonBody.id;
        } else {
            utils.recordError(record, errorType.ORDER_ID);
        }
        // Get order type
        if (jsonBody.hasOwnProperty('delivery')) {
            record.orderType = jsonBody.delivery ? orderType.DELIVERY : orderType.PICKUP;
        } else {
            utils.recordError(record, errorType.ORDER_TYPE);
        }
        // Get order total amount
        if (jsonBody.hasOwnProperty('total')) {
            record.orderAmount = jsonBody.total;
        } else {
            utils.recordError(record, errorType.ORDER_AMOUNT);
        }
        // Get payment type
        if (jsonBody.hasOwnProperty('payment')) {
            record.paymentType = utils.getPaymentType(jsonBody.payment);
        } else {
            utils.recordError(record, errorType.PAYMENT_TYPE);
        }
        // Get phone number
        if (jsonBody.hasOwnProperty('phoneNumber')) {
            record.customerNumber = utils.formatPhoneNumber(jsonBody.phoneNumber);
        } else {
            utils.recordError(record, errorType.CUSTOMER_NUMBER);
        }
        // Get zipcode
        if (jsonBody.hasOwnProperty('zip')) {
            if (jsonBody.zip) {
                record.zipcode = parseInt(jsonBody.zip);
            }
        } else {
            utils.recordError(record, errorType.ZIPCODE);
        }
        // Get state
        if (jsonBody.hasOwnProperty('state')) {
            record.state = utils.shortStateName(jsonBody.state);
        } else {
            utils.recordError(record, errorType.STATE);
        }
        // Get city
        if (jsonBody.hasOwnProperty('city')) {
            record.city = jsonBody.city ? jsonBody.city.toUpperCase() : null;
        } else {
            utils.recordError(record, errorType.CITY);
        }
        // Get street
        if (jsonBody.hasOwnProperty('streetAddress')) {
            record.street = jsonBody.streetAddress ? jsonBody.streetAddress.toUpperCase() : null;
            if (record.street && jsonBody.hasOwnProperty('apartment') && jsonBody.apartment) {
                record.street += ' Apt ' + jsonBody.apartment;
            }
        } else {
            utils.recordError(record, errorType.STREET);
        }
        // Get full address
        record.customerAddress = utils.createFullAddress(record.street, record.city, record.state, record.zipcode);
    } else {
        utils.recordError(record, errorType.JSON_BODY);
    }
    // for errors add the original message text body too
	if (record.error) {
        record.mail = cleanedHtml;
	}
    return record;
}

/**
 * The html body contains a dictionary of the order info embedded in it that we extract from orderInfo div id.
 * @param {string} html - mail html body
 * @returns {null|any}
 */
function getOrderJSON(html) {
    const startTag = '<div id="orderInfo"';
    const startIndex = html.indexOf(startTag);
    if (startIndex !== -1) {
      const endIndex = html.indexOf('</div>', startIndex);
      if (endIndex !== -1) {
        const regex = /({.*})/;
        const match = html.substring(startIndex, endIndex).match(regex);
        if (match) {
          return JSON.parse(match[1]);
        }
      }
    }
    return null;
}


function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords.filter(function(record) { return !record.error;}));
}

module.exports = {createTransactionRecord, createCustomerRecords}