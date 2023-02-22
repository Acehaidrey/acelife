const Papa = require('papaparse');
const fs = require('fs');
const argv = require('yargs')
	.alias('e', 'email-file')
	.alias('d', 'delivery-file')
    .alias('o', 'output')
	.argv;

const {CustomerRecord} = require("./record");
const utils = require("./utils.js");
const {Platform, keyType} = require("./constants");


// TODO: Consider downloading the transaction information from emails to get daily accounting too
function createTransactionRecord(mail) {
    return {};
}

function createCustomerRecords(transactionRecords) {
	return utils.aggregateCustomerHistory(transactionRecords, keyType.NAME);
}

/**
 * Combine the customer email and the customer delivery address csvs from menufy
 * admin dashboard, to produce single array of customer records.
 * @param {string} delAddrFilePath
 * @param {string} custEmailFilePath
 * @param {string} storeName
 * @returns {Promise<unknown>}
 */
function combineCSVFiles(delAddrFilePath, custEmailFilePath, storeName) {
  let data1 = [];
  let data2 = [];
  let data1Records = [];
  let data2Records = [];

  return new Promise((resolve, reject) => {
    fs.readFile(delAddrFilePath, 'utf8', (err, fileContents) => {
      if (err) {
        reject(err);
      }
      data1 = Papa.parse(fileContents, { header: true }).data;
	  data1.forEach(row1 => {
          const name = utils.createFullName(row1['First Name'], row1['Last Name']);
          if (name !== '') {
              const combinedRecord = new CustomerRecord(utils.formatString(storeName), utils.formatPhoneNumber(row1['Phone']));
              combinedRecord.customerNames.add(name);
              combinedRecord.platforms.add(Platform.MENUFY);
              combinedRecord.customerAddresses.add(utils.createFullAddress(row1['Address1'], row1['City'], row1['State'], row1['ZipCode']));
              data1Records.push(combinedRecord);
          }
	  });

      fs.readFile(custEmailFilePath, 'utf8', (err, fileContents) => {
        if (err) {
          reject(err);
        }

        data2 = Papa.parse(fileContents, { header: true }).data;
		data2.forEach(row1 => {
            const name = utils.createFullName(row1['First Name'], row1['Last Name']);
            if (name !== '') {
              const combinedRecord = new CustomerRecord(storeName, null);
              combinedRecord.customerNames.add(utils.createFullName(row1['First Name'], row1['Last Name']));
              combinedRecord.lastOrderDate = row1['Last Order Date'];
              combinedRecord.firstOrderDate = row1['First Order Date'];
              combinedRecord.customerEmails.add(row1['Email']);
              combinedRecord.platforms.add(Platform.MENUFY);
              data2Records.push(combinedRecord);
            }
	    });

        const combinedData = combineCustomerRecords(data1Records, data2Records);
        resolve(combinedData);
      });
    });
  });
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


async function main() {
  const storeName1 = /(aroma|ameci)/i.exec(argv.d)[0].toUpperCase();
  const storeName2 = /(aroma|ameci)/i.exec(argv.e)[0].toUpperCase();
  if (storeName1 !== storeName2) {
    throw new Error('The files store names do not match. Make sure store name is in each filename.')
  }
  try {
    const customerRecords = await combineCSVFiles(argv.d, argv.e, storeName1);
    console.log(customerRecords);
    if (argv.o) {
      utils.saveAsJSON(argv.o, customerRecords);
    }
  } catch (error) {
    console.error(error);
  }
}

module.exports = {createTransactionRecord, createCustomerRecords}


main();