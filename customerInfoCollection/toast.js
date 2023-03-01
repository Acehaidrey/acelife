const utils = require("./utils");
const {CustomerRecord, TransactionRecord} = require("./record");
const {Platform, storeType} = require("./constants");

const argv = require('yargs')
	.alias('i', 'input')
	.argv;


function createTransactionRecord(mail) {
    return {};
}

function createCustomerRecordsFromCSV() {
    let customerRecords = [];
    const data = utils.readCSVFile(argv.i);
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
        // if (phoneNumbers.length > 1) {
        //   console.log(phoneNumbers)
        // }
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