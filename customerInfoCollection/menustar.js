const utils = require("./utils");
const {TransactionRecord} = require("./record");
const {Platform} = require("./constants");

function createTransactionRecord(mail) {
    const record = new TransactionRecord(Platform.MENUSTAR, mail.date);
    console.log(mail);
    // TODO
}

function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords);
}

module.exports = {createTransactionRecord, createCustomerRecords}