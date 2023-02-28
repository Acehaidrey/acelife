const fs = require('fs');
const path = require('path');

const {CustomerRecord} = require("./record");
const utils = require("./utils.js");
const {Platform, storeType} = require("./constants");

// Define the directory to search in
const posDirectory = path.join(process.cwd(), 'Reports', 'POS');

// Define the patterns to search for
const deliveryFilePattern = /Customer_Delivery_Addresses.*-(Aroma|Ameci)\.csv$/i;
const emailFilePattern = /Customer_Emails.*-(Aroma|Ameci)\.csv$/i;

// TODO: Consider downloading the transaction information from emails to get daily accounting too
function createTransactionRecord(mail) {
    return {};
}

// Combine the customer email and the customer delivery address csvs from menufy
// admin dashboard, to produce single array of customer records.
function createCustomerRecords(transactionRecords) {
  // Call the function to search for files and read them
  const retObjects = searchAndReadFiles();
  const deliveryData = retObjects['delivery'];
  const emailData = retObjects['email'];
  const deliveryCustomers = [];
  const emailCustomers = [];

  deliveryData.forEach(record => {
    const name = utils.createFullName(record['First Name'], record['Last Name']);
    if (name) {
        const custRecord = new CustomerRecord(record.storeName, utils.formatPhoneNumber(record['Phone']));
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
    }
  });
  emailData.forEach(record => {
    const name = utils.createFullName(record['First Name'], record['Last Name']);
    if (name) {
      const custRecord = new CustomerRecord(record.storeName, null);
      custRecord.customerNames.add(utils.createFullName(record['First Name'], record['Last Name']));
      custRecord.lastOrderDate = utils.convertTimestampToUTCFormat(record['Last Order Date']);
      custRecord.firstOrderDate = utils.convertTimestampToUTCFormat(record['First Order Date']);
      custRecord.customerEmails.add(record['Email']);
      custRecord.platforms.add(Platform.MENUFY);
      emailCustomers.push(custRecord);
    }
  });
  let combinedCustomerRecords = combineCustomerRecords(deliveryCustomers, emailCustomers);
  const originalCustomerRecords = combinedCustomerRecords.length;
  combinedCustomerRecords = utils.mergeCustomerRecordsByPhoneNumber(combinedCustomerRecords);
  console.log(
      `${deliveryCustomers.length} delivery customer records\n` +
      `${emailCustomers.length} email customer records\n` +
      `${originalCustomerRecords} combined (by store & phone) customer records\n` +
      `${combinedCustomerRecords.length} merged combined records`
  )
  return utils.formatCustomerRecords(combinedCustomerRecords);
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
  let combinedRecords = {};

  // Add records from the first list to the combined object
  for (const record of list1) {
    const customerName = Array.from(record.customerNames)[0];
    combinedRecords[customerName] = record;
  }

  // Add or merge records from the second list to the combined object
  for (const record of list2) {
    const customerName = Array.from(record.customerNames)[0];
    if (combinedRecords[customerName] && record['storeName'] === combinedRecords[customerName]['storeName']) {
      // If the customer already exists, merge the records if the store name matches
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
  combinedRecords = utils.mergeCustomerRecordsByPhoneNumber(Object.values(combinedRecords));
  return utils.formatCustomerRecords(combinedRecords);
}

/**
 * Search for files matching and read their data to join and create a customer data set.
 * @returns {*}
 */
function searchAndReadFiles() {
  // Initialize the lists to store the results
  const deliveryAddresses = [];
  const customerEmails = [];
  // Read the contents of the directory
  const files = fs.readdirSync(posDirectory);
  if (!files) {
    console.error(`Error reading directory: ${err}`);
    return;
  }
  // Filter the files based on the patterns
  const deliveryFiles = files.filter(file => deliveryFilePattern.test(file));
  const emailFiles = files.filter(file => emailFilePattern.test(file));
  // Read the delivery address files
  deliveryFiles.forEach(file => {
    const filePath = path.join(posDirectory, file);
    const ddata = utils.readCSVFile(filePath);
    ddata.forEach((row) => {
      row.storeName = filePath.includes('-Aroma.csv') ? storeType.AROMA : storeType.AMECI;
    });
    deliveryAddresses.push(ddata);
  });
  // Read the customer email files
  emailFiles.forEach(file => {
    const filePath = path.join(posDirectory, file);
    const edata = utils.readCSVFile(filePath);
    edata.forEach((row) => {
      row.storeName = filePath.includes('-Aroma.csv') ? storeType.AROMA : storeType.AMECI;
    });
    customerEmails.push(edata);
  });
  return {'email': [].concat(...customerEmails), 'delivery': [].concat(...deliveryAddresses)}
}

module.exports = {createTransactionRecord, createCustomerRecords}