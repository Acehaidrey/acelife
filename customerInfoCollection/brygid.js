const utils = require("./utils");
const {CustomerRecord} = require("./record");
const {Platform, errorType, orderType, storeType} = require("./constants");
const fs = require("fs");
const Papa = require("papaparse");

const argv = require('yargs')
	.alias('i', 'input')
	.alias('o', 'output')
	.demand(['i'])
	.argv;


// TODO: Consider downloading the transaction information to get daily accounting too
function createTransactionRecord(mail) {
    return {};
}

function createCustomerRecords(transactionRecords) {
    const customerRecords = [];
    const csvData = fs.readFileSync(argv.i, 'utf-8');
    const { data } = Papa.parse(csvData, { header: true });
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
          customerRecord.lastOrderDate = convertTimestampToUTCFormat(record['DATE']);
          // customerRecord.firstOrderDate = customerRecord.lastOrderDate;
          customerRecord.orderCount = parseInt(record['ORDERS']);
          customerRecord.totalSpend = parseFloat(record['PURCHASE'].replace('$', ''));
          if (record['STREET'] && record['SUITE_APT']) {
              record['STREET'] += ' #' + record['SUITE_APT'];
          }
          const addr = utils.createFullAddress(record['STREET'], record['CITY'], record['STATE'], record['ZIP']);
          customerRecord.customerAddresses.add(addr);
          customerRecords.push(customerRecord);
      }

    });

    return utils.formatCustomerRecords(customerRecords);
}


function convertTimestampToUTCFormat(inputDateString) {
    if (!inputDateString) {
        return null;
    }
    return new Date(inputDateString).toISOString();
}

module.exports = {createTransactionRecord, createCustomerRecords}