const Papa = require('papaparse');
const fs = require('fs');
const argv = require('yargs')
	.alias('e', 'email-file')
	.alias('d', 'delivery-file')
	.argv;

const {CustomerRecord} = require("./record");
const utils = require("./utils.js");
const {Platform} = require("./constants");


// TODO: Consider downloading the transaction information from emails to get daily accounting too
function createTransactionRecord(mail) {
    return {};
}

// Combine the customer email and the customer delivery address csvs from menufy
// admin dashboard, to produce single array of customer records.
function createCustomerRecords(transactionRecords) {
  const storeName = getStoreName();
  const deliveryCustomers = [];
  const csvDeliveryData = fs.readFileSync(argv.d, 'utf-8');
  const deliveryData = Papa.parse(csvDeliveryData, { header: true }).data;
  deliveryData.forEach(record => {
      const name = utils.createFullName(record['First Name'], record['Last Name']);
      if (name) {
          const custRecord = new CustomerRecord(utils.formatString(storeName), utils.formatPhoneNumber(record['Phone']));
          custRecord.platforms.add(Platform.MENUFY);
          custRecord.customerNames.add(name);
          if (record['Address1'] && record['Address2'] && !record['Address1'].toLowerCase().includes(record['Address2'].toLowerCase())) {
              record['Address1'] += ' #' + record['Address2'].replace('#', '');
          }
          const addr = utils.createFullAddress(
              record['Address1'],
              record['City'],
              record['State'],
              utils.getZipForCity(record['ZipCode'], record['City'])
          )
          custRecord.customerAddresses.add(addr);
          deliveryCustomers.push(custRecord);
          console.log(record, custRecord)
      }
  });
  const emailCustomers = [];
  const csvEmailData = fs.readFileSync(argv.e, 'utf-8');
  const emailData = Papa.parse(csvEmailData, { header: true }).data;
  emailData.forEach(record => {
    const name = utils.createFullName(record['First Name'], record['Last Name']);
    if (name) {
      const custRecord = new CustomerRecord(storeName, null);
      custRecord.customerNames.add(utils.createFullName(record['First Name'], record['Last Name']));
      custRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record['Last Order Date']);
      custRecord.firstOrderDate = utils.convertTimestampToUTCFormat(record['First Order Date']);
      custRecord.customerEmails.add(record['Email']);
      custRecord.platforms.add(Platform.MENUFY);
      emailCustomers.push(custRecord);
      console.log(record, custRecord)
    }
  });
  let combinedCustomerRecords = combineCustomerRecords(deliveryCustomers, emailCustomers);
  const originalCustomerRecords = combinedCustomerRecords.length;
  console.log(
      `${deliveryCustomers.length} delivery customer records\n` +
      `${emailCustomers.length} email customer records\n` +
      `${originalCustomerRecords} combined customer records\n`
  )
  return utils.formatCustomerRecords(combinedCustomerRecords);
}

/**
 * Get the store name from the files exported. Expecting storename in the files downloaded.
 * If there is a mismatch, then fail.
 * @returns {string}
 */
function getStoreName() {
  const storeName1 = /(aroma|ameci)/i.exec(argv.d)[0].toUpperCase();
  const storeName2 = /(aroma|ameci)/i.exec(argv.e)[0].toUpperCase();
  if (storeName1 !== storeName2) {
    throw new Error('The files store names do not match. Make sure store name is in each filename.')
  }
  return storeName1;
}

/**
 * Combine two lists of customer records into one list merging the common
 * contacts. It joins on the customer name to combine. This will have all the
 * list1 and list2 and merge on their overlaps.
 * @param {CustomerRecord[]} list1
 * @param {CustomerRecord[]} list2
 * @returns {CustomerRecord[]}
 */
function combineCustomerRecords(list1, list2) {
  // Create an object to store combined records by customer name
  const combinedRecords = {};

  // Add records from the first list to the combined object
  for (const record of list1) {
    const customerName = Array.from(record.customerNames)[0];
    combinedRecords[customerName] = record;
  }

  // Add or merge records from the second list to the combined object
  for (const record of list2) {
    const customerName = Array.from(record.customerNames)[0];
    if (combinedRecords[customerName]) {
      // If the customer already exists, merge the records
      const existingRecord = combinedRecords[customerName];
      existingRecord.lastOrderDate = record.lastOrderDate;
      existingRecord.firstOrderDate = record.firstOrderDate;
      existingRecord.customerEmails = record.customerEmails;
    } else {
      // If the customer doesn't exist, add the record
      combinedRecords[customerName] = record;
    }
  }
  // Convert the object back to an array of records
  return utils.formatCustomerRecords(Object.values(combinedRecords));
}

module.exports = {createTransactionRecord, createCustomerRecords}