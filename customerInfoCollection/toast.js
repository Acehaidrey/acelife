const utils = require("./utils");
const {CustomerRecord, TransactionRecord} = require("./record");
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

      if (record.phones) {
        const phoneNumbers = record.phones.split(';');
        phoneNumbers.forEach(phone => {
          if (phone) {
            const customerRecord = new CustomerRecord(storeType.AROMA, utils.formatPhoneNumber(phone.trim()));
            customerRecord.platforms.add(Platform.TOAST);
            customerRecord.customerNames.add(utils.createFullName(record.firstName, record.lastName));
            customerRecord.orderCount = parseInt(record.totalVisits);
            customerRecord.totalSpend = parseFloat(record.averageSpend) * customerRecord.orderCount;
            // customerRecord.customerAddresses.add();
            // customerRecord.firstOrderDate = null;
            customerRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record.lastVisitDate);
            if (record.emails) {
              const emails = record.emails.split(';');
              emails.forEach(email => {
                if (email) {
                  customerRecord.customerEmails.add(email.trim());
                }
              });
            }
            if (!utils.customerInformationMissing(customerRecord)) {
                customerRecords.push(customerRecord);
            }
          }
        });
      } else if (!record.customerNumber) {
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
        if (!utils.customerInformationMissing(customerRecord)) {
            customerRecords.push(customerRecord);
        }
      }
    });
    const originalLength = customerRecords.length;
    customerRecords = utils.mergeCustomerRecordsByPhoneNumber(customerRecords);
    console.log(
      `${originalLength} original customer records found.\n` +
      `${customerRecords.length} customer records found after merging.`
    );
    return utils.formatCustomerRecords(customerRecords);
}

module.exports = {createTransactionRecord, createCustomerRecords}