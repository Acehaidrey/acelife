const utils = require("./utils");
const {CustomerRecord, TransactionRecord} = require("./record");
const {Platform, storeType} = require("./constants");
const fs = require("fs");
const Papa = require("papaparse");

const argv = require('yargs')
	.alias('i', 'input')
	.argv;


function createTransactionRecord(mail) {
    const record = new TransactionRecord(Platform.TOAST, mail.date);
    console.log(mail);
    return null;
}

function createCustomerRecords(transactionRecords) {
    let customerRecords = [];
    const csvData = fs.readFileSync(argv.i, 'utf-8');
    const { data } = Papa.parse(csvData, { header: true });
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
      console.log(record)

      if (record.phones) {
        const phoneNumbers = record.phones.split(';');
        if (phoneNumbers.length > 1) {
            console.log(phoneNumbers);
        }
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
    customerRecords = utils.mergeCustomerRecords(customerRecords);
    console.log(`Originally had ${originalLength} customer records, merged alike to ${customerRecords.length} records.`)
    return utils.formatCustomerRecords(customerRecords);
}

module.exports = {createTransactionRecord, createCustomerRecords}