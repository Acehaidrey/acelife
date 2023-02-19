const {Platform, PaymentType, keyType} = require("./constants");
const {TransactionRecord} = require("./record");
const utils = require("./utils");

const regexCustomerName = /from (.*) for/;
const regexStoreName = /for (Aroma|Ameci)/i;
const regexOrderId = /Order #\s*(\w+)/;

// TODO: Figure out how to parse the attachment in synchronous way to get total amount and order type
function createTransactionRecord(mail) {
    const record = new TransactionRecord(Platform.DOORDASH, mail.date);
    const subj = mail.subject;
    // Extract customer name
    const customerNameMatch = subj.match(regexCustomerName);
    if (customerNameMatch) {
        record.customerName = utils.formatString(customerNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, 'Could not parse customer name.');
	}
    // Extract store name
    const storeNameMatch = subj.match(regexStoreName);
    if (storeNameMatch) {
        record.storeName = utils.formatString(storeNameMatch[1].toUpperCase());
    } else {
		utils.recordError(record, 'Could not parse store name.');
	}
    // Extract order id
    const orderIdMatch = subj.match(regexOrderId);
    if (storeNameMatch) {
        record.orderId = utils.formatString(orderIdMatch[1]);
    } else {
		utils.recordError(record, 'Could not parse order id.');
	}
    // set payment type to credit always
    record.paymentType = PaymentType.CREDIT;

    return record;
}

function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords, keyType.NAME);
}


module.exports = {createTransactionRecord, createCustomerRecords}