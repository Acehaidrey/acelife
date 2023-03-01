const utils = require("./utils");
const {CustomerRecord} = require("./record");
const {Platform, storeType} = require("./constants");

const argv = require('yargs')
	.alias('i', 'input')
	.argv;


function createTransactionRecord(mail) {
    return {};
}

function createCustomerRecords(transactionRecords) {
    let customerRecords = [];
    const data = utils.readCSVFile(argv.i);
    data.forEach((record) => {
      // replace the null string representations to real null values
      for (const prop in record) {
        if (record[prop] === '' || record[prop] === 'NULL' || record[prop] === 'N/A') {
            if (prop === 'TotalOrderValue' || prop === 'TotalOrders') {
                record[prop] = '0';
            } else {
                record[prop] = null;
            }
        } else if (record[prop]) {
            record[prop] = record[prop].trim();
        }
      }
      const customerRecord = new CustomerRecord(storeType.AMECI, utils.formatPhoneNumber(record['Phone']));
      customerRecord.platforms.add(Platform.SPEEDLINE);
      customerRecord.customerNames.add(utils.createFullName(record['FirstName'], record['LastName']));
      customerRecord.customerEmails.add(record['Email']);
      customerRecord.firstOrderDate = utils.convertTimestampToUTCFormat(record['FirstOrder']);
      customerRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record['LastOrder']);
      customerRecord.orderCount = parseInt(record['TotalOrders']);
      customerRecord.totalSpend = parseFloat(record['TotalOrderValue']);
      let street = '';
      if (record['StreetNumber']) {
          street += utils.formatString(record['StreetNumber']);
      } if (record['StreetName']) {
          street += ' ' + utils.formatString(record['StreetName']);
      } if (record['Apartment']) {
          street += ' #' + utils.formatString(record['Apartment']).replace('#', '');
      }
      if (street) {
        const addr = utils.createFullAddress(street, record['City'], utils.shortStateName(record['State']), utils.getZipForCity(record['Zip'], record['City']));
        customerRecord.customerAddresses.add(addr);
      }
      if (!utils.customerInformationMissing(customerRecord)) {
        customerRecords.push(customerRecord);
      }
    });
    const originalLength = customerRecords.length;
    customerRecords = utils.mergeCustomerRecordsByPhoneNumber(customerRecords);
    console.log(
        `[SPEEDLINE] ${originalLength} original customer records found.\n` +
        `[SPEEDLINE] ${customerRecords.length} customer records found after merging.`
      );
    return customerRecords;
}

module.exports = {createTransactionRecord, createCustomerRecords}