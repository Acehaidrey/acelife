const utils = require("./utils");
const {TransactionRecord} = require("./record");
const {Platform, PaymentType, errorType, orderType} = require("./constants");


const regexStoreName = /(ameci|aroma)/i;
const regexOrderId = /Order Number:\s+([^<\s]+(?:\s+[^<\s]+)*)/;
const regexPhoneNumber = /Phone Number:\s*\((\d{3})\)\s*(\d{3})-(\d{4})/;
const regexCustomerName = /<td[^>]*>\s*Customer:\s*(.*?)\s*<\/td>/i;
const regexOrderType = /<span>(FUTURE\s+)?(Pickup|Delivery)\s*<\/span>/i;
const regexOrderTypeBackup = /(pickup|delivery)\.png/; // being lazy and check this if expression doesn't match above
const regexPaymentType = /PLEASE CHARGE|DO NOT CHARGE/;
const regexOrderTotal = /Total:[^$]*\$(\d+\.\d{2})/;
const regexAddress = /Delivery Address:<\/div>\s*<div>([\s\S]{1,50}?)\s*,\s*<br\/>([\s\S]{1,50}?)\s*,\s*([A-Z]{2})\s*(\d{5})?/;


function createTransactionRecord(mail) {
    const cleanedHtml = utils.formatString(mail.html);
    const record = new TransactionRecord(Platform.MENUSTAR, mail.date);
    // Get store name
    const storeNameMatch = cleanedHtml.match(regexStoreName);
    if (storeNameMatch) {
        record.storeName = utils.formatString(storeNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, errorType.STORE_NAME);
	}
    // Get order id
    const orderIdMatch = cleanedHtml.match(regexOrderId);
    if (orderIdMatch) {
        record.orderId = utils.formatString(orderIdMatch[1]);
    } else {
		utils.recordError(record, errorType.ORDER_ID);
	}
    // Get order type
    const orderTypeMatch = cleanedHtml.match(regexOrderType);
    const orderTypeMatchBackup = cleanedHtml.match(regexOrderTypeBackup);
    if (orderTypeMatch) {
        record.orderType = utils.formatString(orderTypeMatch[2].toUpperCase());
    } else {
        if (orderTypeMatchBackup) {
            record.orderType = utils.formatString(orderTypeMatchBackup[1].toUpperCase());
        } else {
            utils.recordError(record, errorType.ORDER_TYPE);
        }
	}
    // Get payment type
    const paymentTypeMatch = cleanedHtml.match(regexPaymentType);
    if (paymentTypeMatch && getPaymentType(paymentTypeMatch[0])) {
        record.paymentType = getPaymentType(paymentTypeMatch[0]);
    } else {
		utils.recordError(record, errorType.PAYMENT_TYPE);
	}
    // Get phone number
    const phoneNumberMatch = cleanedHtml.match(regexPhoneNumber);
    if (phoneNumberMatch) {
        const areaCode = phoneNumberMatch[1];
        const prefix = phoneNumberMatch[2];
        const lineNumber = phoneNumberMatch[3];
        const phoneNumber = `${areaCode}-${prefix}-${lineNumber}`;
        record.customerNumber = utils.formatPhoneNumber(phoneNumber);
    } else {
		utils.recordError(record, errorType.CUSTOMER_NUMBER);
	}
    // Get customer name
    const customerNameMatch = cleanedHtml.match(regexCustomerName);
    if (customerNameMatch) {
        record.customerName = utils.formatString(customerNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, errorType.CUSTOMER_NAME);
	}
    // Get order total amount
    const orderTotal = cleanedHtml.match(regexOrderTotal);
    if (orderTotal && orderTotal[1]) {
        record.orderAmount = parseFloat(orderTotal[1]);
    } else {
		utils.recordError(record, errorType.ORDER_AMOUNT);
	}
    // Get address if delivery
    const addressMatch = cleanedHtml.match(regexAddress);
    if (addressMatch) {
        record.street = addressMatch[1].trim().toUpperCase();
        record.city = addressMatch[2].trim().toUpperCase();
        record.state = utils.shortStateName(addressMatch[3].trim());
        record.zipcode = addressMatch[4] ? parseInt(addressMatch[4].trim()) : null;
        record.customerAddress = utils.createFullAddress(record.street, record.city, record.state, record.zipcode);
    } else {
        if (record.orderType === orderType.DELIVERY) {
            utils.recordError(record, errorType.CUSTOMER_ADDRESS);
        }
	}
    // for errors add the original message text body too
	if (record.error) {
        record.mail = cleanedHtml;
	}

    return record;
}

function getPaymentType(input) {
    /**
     * Helper function to get the payment type as cash or credit based on the string specific to menustar.
     */
    if (input === 'PLEASE CHARGE') {
        return PaymentType.CASH;
    } else if (input === 'DO NOT CHARGE') {
        return PaymentType.CREDIT;
    }
    return null;
}


function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords.filter(function(record) { return !record.error;}));
}

module.exports = {createTransactionRecord, createCustomerRecords}