const utils = require("./utils");
const {CustomerRecord} = require("./record");
const {Platform, storeType} = require("./constants");

const argv = require('yargs')
	.alias('i', 'input')
	.argv;


// TODO: Consider downloading the transaction information from emails to get daily accounting too
function createTransactionRecord(mail) {
    return {};
}

// Brygid we get the file from the site, download 6 months worth customer data, and parse csv info
function createCustomerRecords(transactionRecords) {
    const customerRecords = [];
    const data = utils.readCSVFile(argv.i);
    data.forEach((record) => {
      // replace the null string representations to real null values
      for (const prop in record) {
        if (record[prop] === '' || record[prop] === 'NULL' || record[prop] === 'N/A') {
          record[prop] = null;
        } else if (prop === 'PURCHASE' && !record[prop]) {
            record[prop] = '0';
        } else if (prop === 'ORDERS' && !record[prop]) {
            record[prop] = '0';
        }
      }
      if (record['STORE']) {
          const customerRecord = new CustomerRecord(storeType.AMECI, utils.formatPhoneNumber(record['PHONE']));
          customerRecord.platforms.add(Platform.BRYGID);
          customerRecord.customerNames.add(utils.createFullName(record['FIRST_NAME'], record['LAST_NAME']));
          customerRecord.customerEmails.add(record['EMAIL']);
          customerRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record['DATE']);
          customerRecord.orderCount = parseInt(record['ORDERS']);
          customerRecord.totalSpend = parseFloat(record['PURCHASE'].replace('$', ''));
          if (record['STREET'] && record['SUITE_APT']) {
              record['STREET'] += ' #' + record['SUITE_APT'];
          }
          const addr = utils.createFullAddress(record['STREET'], record['CITY'], utils.shortStateName(record['STATE']), record['ZIP']);
          customerRecord.customerAddresses.add(addr);
          customerRecords.push(customerRecord);
      }
    });
    return utils.formatCustomerRecords(customerRecords);
}

module.exports = {createTransactionRecord, createCustomerRecords}