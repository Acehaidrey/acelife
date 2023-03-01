const Papa = require('papaparse');
const fuzzy = require("fuzzball");
const fs = require("fs");
const path = require('path');
const {CustomerRecord, TransactionRecord} = require("./record");
const {SIMILARITY_THRESHOLD, keyType, paymentType, Platform, errorType} = require("./constants");

/**
 * For names and addresses, users occasionally misspell the results. We want to filter
 * out cases where there is this overlap. We identify records that have an 80% match
 * (threshold below) from a list. We pick the first value for that match only to add.
 * Uses edit distance to compare.
 * @param {*[]} list
 * @returns {*[]|*}
 */
function removeSimilarValues(list) {
	if (list.length <= 1) {
		return list;
	}

	const uniqueAddresses = [];
	for (let i = 0; i < list.length; i++) {
		let add = list[i];
		let isDuplicate = false;
		for (let j = i + 1; j < list.length; j++) {
			let compareTo = list[j];
			let ratio = fuzzy.ratio(add, compareTo);
			if (ratio > SIMILARITY_THRESHOLD) {
				isDuplicate = true;
				break;
			}
		}
		if (!isDuplicate) {
			uniqueAddresses.push(add);
		}
	}
	return uniqueAddresses;
}

/**
 * Convert the state name to the short name. Our orders should all be in CA so.
 * @param {string|null} stateName
 * @returns {string|*}
 */
function shortStateName(stateName) {
	if (stateName === null || stateName === undefined) {
		return stateName;
	}
	stateName = stateName.toUpperCase();
	if (stateName === 'CALIFORNIA') {
		return 'CA';
	}
	return stateName;
}

/**
 * If the zipcode is null but there is a city set, then infer it from this hard coded map.
 * @param {int|string|null} zipcode
 * @param {string|null} cityName
 * @returns {int|*}
 */
function getZipForCity(zipcode, cityName) {
	if (zipcode) {
		return zipcode;
	}
	if (cityName === null || cityName === undefined) {
		return cityName;
	}
	cityName = cityName.toUpperCase();
	if (cityName === 'LAKE FOREST') {
		return 92630;
	}
	return null;
}

/**
 * Record an error message and mark the record had an error parsing the record.
 * @param {TransactionRecord} record
 * @param {string} errorMsg
 */
function recordError(record, errorMsg) {
	record.error = true;
	record.errorReason.push(errorMsg);
}

/**
 * Cleans a string to replace non-ascii characters and removes \r from the string.
 * Removes multiple white spaces to put just one. Trims the string.
 * @param {string|null} str
 * @returns {string|*}
 */
function formatString(str) {
	if (str === null || str === undefined || !str) {
		return str;
	}
	return str.replaceAll('=0D', '')
		.replaceAll('=3D', '')
		.replaceAll('\r', '')
		.replace(/\s+/g,' ')
		.trim();
}

/**
 * Cleans a string to replace non-ascii characters and removes \r from the string. Creates an int value for phone.
 * @param {string|null} phoneNumber
 * @returns {number|*}
 */
function formatPhoneNumber(phoneNumber) {
	if (phoneNumber === null || phoneNumber === undefined) {
		return phoneNumber;
	}
	let cleanedNum = phoneNumber.trim()
		.replace('1(', '(')
		.replace('+1', '')
		.replace(/\D/g, '');
	if (cleanedNum && cleanedNum.length > 10) {
		cleanedNum = cleanedNum.substring(cleanedNum.length - 10, cleanedNum.length);
	}
	return parseInt(cleanedNum);
}

/**
 * Given all the separated address info, create one formatted address string.
 * @param {string|null} street
 * @param {string|null} city
 * @param {string|null} state
 * @param {string|int|null} zip
 * @returns {string}
 */
function createFullAddress(street, city, state, zip) {
	let fullAddress = '';
	if (street !== null && street !== undefined) {
		fullAddress = formatString(street.toUpperCase()) + ', ';
	}
	if (city !== null && city !== undefined) {
		fullAddress += formatString(city.toUpperCase()) + ', ';
	}
	if (state !== null && state !== undefined) {
		fullAddress += shortStateName(state) + ' ';
	}
	if (zip !== null && zip !== undefined) {
		fullAddress += zip;
	}

	return fullAddress.trim().replace(/^,+|,+$|(?<=,) +(?=,)/g, "");
}

/**
 * Given a first name and last name to create a single joined name.
 * @param {string|null} firstName
 * @param {string|null} lastName
 * @returns {string|null}
 */
function createFullName(firstName, lastName) {
	let fullName = '';
	if (firstName !== null && firstName !== undefined) {
		fullName = firstName.toUpperCase() + ' ';
	}
	if (lastName !== null && lastName !== undefined) {
		fullName += lastName.toUpperCase();
	}
	return fullName ? fullName.trim() : null;
}

/**
 * Helper function to save an object as a JSON.
 * @param {string} outputPath - output path to save the json file to
 * @param {*} obj - object to serialize as JSON
 */
function saveAsJSON(outputPath, obj) {
	if (!path.isAbsolute(outputPath)) {
	  // If it's not absolute, join it with the ./Reports directory path
	  outputPath = path.join('./Reports', outputPath);
	}
	if (!outputPath.endsWith('.json')) {
	  outputPath += '.json';
	}
	fs.writeFile(outputPath, JSON.stringify(obj), function(err) {
		if(err)
			return console.log(err);
	});
}

/**
 * Takes the list of TransactionRecord and aggregates them. It creates a list of CustomerRecords.
 * This assumes that the TransactionRecords are clean properly and won't have issues.
 * @param {TransactionRecord[]} records - transaction records to join on
 * @param {keyType} keyIdentifier - parameter type to use for the key to join on
 * @returns {CustomerRecord[]} - list of customer records after combining
 */
function aggregateCustomerHistory(records, keyIdentifier = keyType.PHONE) {
	const keyName = keyIdentifier === keyType.NAME ? 'customerName' : 'customerNumber';
	const nullRecords = records.filter(function(record) { return !record[keyName]});
	const validRecords = records.filter(function(record) { return record[keyName]});

	const combinedRecords = {};
	for (const record of validRecords) {
	  const key = `${record.storeName}-${record[keyName]}`;

	  if (!combinedRecords[key]) {
		combinedRecords[key] = new CustomerRecord(record.storeName, record.customerNumber);
		combinedRecords[key].lastOrderDate = record.orderDate;
		combinedRecords[key].firstOrderDate = record.orderDate;
		combinedRecords[key].platforms.add(record.platform);
		combinedRecords[key].customerNames.add(record.customerName);
	  }
	  combinedRecords[key].platforms.add(record.platform);
	  combinedRecords[key].customerNames.add(record.customerName);
	  combinedRecords[key].lastOrderDate = combinedRecords[key].lastOrderDate > record.orderDate ? combinedRecords[key].lastOrderDate : record.orderDate;
	  combinedRecords[key].firstOrderDate = combinedRecords[key].firstOrderDate < record.orderDate ? combinedRecords[key].firstOrderDate : record.orderDate;
	  combinedRecords[key].customerAddresses.add(record.customerAddress);
	  combinedRecords[key].customerEmails.add(record.customerEmail);
	  combinedRecords[key].orderCount += 1;
	  combinedRecords[key].totalSpend += record.orderAmount;
	}
	for (const nullRecord in nullRecords) {
		const count = 0; // add a random key
		combinedRecords[count] = new CustomerRecord(nullRecord.storeName, nullRecord.customerNumber);
		combinedRecords[count].platforms.add(nullRecord.platform);
		combinedRecords[count].customerNames.add(nullRecord.customerName);
		combinedRecords[count].lastOrderDate = combinedRecords[count].lastOrderDate > nullRecord.orderDate ? combinedRecords[count].lastOrderDate : nullRecord.orderDate;
		combinedRecords[count].firstOrderDate = combinedRecords[count].firstOrderDate < nullRecord.orderDate ? combinedRecords[count].firstOrderDate : nullRecord.orderDate;
		combinedRecords[count].customerAddresses.add(nullRecord.customerAddress);
		combinedRecords[count].customerEmails.add(nullRecord.customerEmail);
		combinedRecords[count].orderCount += 1;
		combinedRecords[count].totalSpend += nullRecord.orderAmount;
	}
	return formatCustomerRecords(Object.values(combinedRecords));
}

/**
 * Get the platform name from the input paths of the mbox files. If filename prefixed with Orders-
 * because it is a sub label, then we strip it out.
 * @param {string|null} inputPath - input filepath
 * @returns {Platform|null} - Platform name
 */
function getPlatform(inputPath) {
	if (inputPath === null || inputPath === undefined || !inputPath) {
		return null;
	}
	if (inputPath.toLowerCase().includes('customer_email') || inputPath.toLowerCase().includes('delivery_address')) {
		return Platform.MENUFY;
	}
	let partner = inputPath.match(/([^/]+)\.mbox$/);
	if (!partner) {
		partner = inputPath.match(/([^/]+)\.csv$/);
	}
	if (partner) {
		partner = partner[1];
		if (partner.startsWith('Orders-')) {
			partner = partner.replace(/^Orders-/, '');
		}
		if (partner.match(/^[^-]*/)) {
			partner = partner.match(/^[^-]*/)[0];
		}
	}
	return partner.toUpperCase();
}

/**
 * Format customer records sets into lists and remove similar values, round the values to two decimal places.
 * @param {CustomerRecord[]} records - the list of records to format Sets to Arrays and other formatting
 * @returns {CustomerRecord[]} - the formatted list
 */
function formatCustomerRecords(records) {
	for (const record of records) {
		record.customerNames = removeSimilarValues(Array.from(record.customerNames).filter(function(val) { return val !== null && val !== ''}));
		record.customerNames = removeSubsets(record.customerNames);
		record.customerAddresses = removeSimilarValues(Array.from(record.customerAddresses).filter(function(val) { return val !== null && val !== '' }));
		record.customerEmails = Array.from(record.customerEmails).filter(function(val) { return val !== null && val !== '' });
		record.platforms = Array.from(record.platforms).filter(function(val) { return val !== null && val !== '' });
		record.totalSpend = parseFloat(record.totalSpend.toFixed(2));
	}
	return records;
}

/**
 * Removes subsets for names so that if we have the name [Mike, Mike Malone], we remove the name Mike.
 * @param {string[]} customerNames 
 * @returns {string[]}
 */
function removeSubsets(customerNames) {
	const sortedNames = customerNames.sort((a, b) => b.length - a.length);
	const uniqueNames = sortedNames.filter((name, index) => {
	  for (let i = 0; i < index; i++) {
		if (sortedNames[i].includes(name)) {
		  return false;
		}
	  }
	  return true;
	});
	return uniqueNames;
}

/**
 * Merges duplicate records based on the orderId field, selecting non-null or non-undefined
 * values for other fields, or the first value arbitrarily if both are null/undefined.
 * Removes the other record from the list.
 * @param {TransactionRecord[]} records - the list of records to merge
 * @returns {TransactionRecord[]} - the merged list of records
 */
function mergeRecords(records) {
  const mergedRecords = [];
  const seenOrderIds = new Set();

  for (const record of records) {
    if (!record.orderId || seenOrderIds.has(record.orderId)) {
      continue;
    }
    const duplicateRecords = records.filter((r) => r.orderId === record.orderId);
    let mergedRecord = new TransactionRecord(record.platform, record.orderDate);

    for (const field of Object.keys(mergedRecord)) {
      const values = duplicateRecords.map((r) => r[field]).filter((value) => value !== null && value !== undefined);
      if (values.length > 0) {
        mergedRecord[field] = values[0];
      }
    }
    mergedRecords.push(mergedRecord);
    seenOrderIds.add(record.orderId);
  }

  return mergedRecords;
}

/**
 * Helper function to get the payment type as cash or credit based on the string specific to menustar/eatstreet.
 * @param {string} input - Input string to check matches on
 * @returns {paymentType|null}
 */
function getPaymentType(input) {
    if (input === 'PLEASE CHARGE' || input === 'COLLECT PAYMENT') {
        return paymentType.CASH;
    } else if (input === 'DO NOT CHARGE') {
        return paymentType.CREDIT;
    }
    return null;
}

/**
 * The emails generally have some back and forth emails that we have with support. Those emails generally
 * are false records vs true error records. If a record is in the transactionRecords already, if an orderId
 * is already in the transactionRecords, then any record with same orderId in the error list is extraneous
 * and causing noise, so we want to filter these out.
 * @param {TransactionRecord[]} transactionRecords
 * @param {TransactionRecord[]} errorRecords
 * @returns {TransactionRecord[]}
 */
function removeFalseErrorRecords(transactionRecords, errorRecords) {
	const orderIds = new Set(transactionRecords.filter(record => record.orderId !== null).map(record => record.orderId));
	return errorRecords.filter(record => record.orderId !== null && 
		!orderIds.has(record.orderId) && 
		!record.errorReason.includes(errorType.NOT_TRANSACTION_EMAIL));
}

/**
 * Convert a string of form 01/09/2023 or other to 2023-01-09T00:00:00.000Z.
 * @param {string} inputDateString
 * @returns {string|null}
 */
function convertTimestampToUTCFormat(inputDateString) {
    if (!inputDateString) {
        return null;
    }
    return new Date(inputDateString).toISOString();
}

/**
 * Merge customer records matching same phone number. Separate by store still.
 * Does not combine the null phone numbers and treats them as separate records.
 * @param {CustomerRecord[]} records
 * @returns {CustomerRecord[]}
 */
function mergeCustomerRecordsByPhoneNumber(records) {
  const customerRecords = {};
  const nullPhoneRecords = records.filter(function(record) { return !record.customerNumber});
  const validPhoneRecords = records.filter(function(record) { return record.customerNumber});

  for (const record of validPhoneRecords) {
	const key = `${record.storeName}-${record.customerNumber}`;
    let mergedRecord = customerRecords[key];

    if (!mergedRecord) {
      mergedRecord = new CustomerRecord(record.storeName, record.customerNumber);
      customerRecords[key] = mergedRecord;
    }

    mergedRecord.platforms = new Set([...record.platforms, ...mergedRecord.platforms]);
	mergedRecord.customerNames = new Set([...record.customerNames, ...mergedRecord.customerNames]);
	mergedRecord.customerAddresses = new Set([...record.customerAddresses, ...mergedRecord.customerAddresses]);
	mergedRecord.customerEmails = new Set([...record.customerEmails, ...mergedRecord.customerEmails]);
    mergedRecord.orderCount += record.orderCount;
    mergedRecord.totalSpend += record.totalSpend;

    if (!mergedRecord.firstOrderDate || record.firstOrderDate < mergedRecord.firstOrderDate) {
      mergedRecord.firstOrderDate = record.firstOrderDate;
    }

    if (!mergedRecord.lastOrderDate || record.lastOrderDate > mergedRecord.lastOrderDate) {
      mergedRecord.lastOrderDate = record.lastOrderDate;
    }
	mergedRecord.platforms.delete(null);
	mergedRecord.customerNames.delete(null);
	mergedRecord.customerAddresses.delete(null);
	mergedRecord.customerEmails.delete(null);
  }
  return formatCustomerRecords(Object.values(customerRecords).concat(nullPhoneRecords));
}

/**
 * Find duplicate records based on the customer phone number.
 * @param {CustomerRecord[]|TransactionRecord[]} customers
 * @returns {CustomerRecord[]|TransactionRecord[]}
 */
function findDuplicateCustomerNumbers(customers) {
  const customerNumbers = customers.map(customer => customer.customerNumber);
  const uniqueCustomerNumbers = new Set(customerNumbers);
  const duplicateCustomerNumbers = [...customerNumbers.filter(customerNumber => {
    if (uniqueCustomerNumbers.has(customerNumber)) {
      uniqueCustomerNumbers.delete(customerNumber);
    } else {
      return true;
    }
  })];
  return duplicateCustomerNumbers;
}

/**
 * If the record is missing name, number, address and email, then it is not useful record.
 * We delete null values from the lists first.
 * @param {CustomerRecord} record
 * @returns {boolean}
 */
function customerInformationMissing(record) {
	record.customerNames.delete(null);
	record.customerAddresses.delete(null);
	record.customerEmails.delete(null);
    return !record.customerNumber &&
        record.customerNames.size === 0 &&
        record.customerAddresses.size === 0 &&
        record.customerEmails.size === 0
}

/**
 * Takes the year/month/date and creates string in format YYYY-MM-DD.
 * @param {Date} dt 
 * @returns {string}
 */
function formatDate(dt) {
	const year = dt.getFullYear();
	const month = String(dt.getMonth() + 1).padStart(2, '0');
	const day = String(dt.getDate()).padStart(2, '0');
	return `${year}-${month}-${day}`;
}

/**
 * Read a CSV file and return the data of it.
 * @param {string} filePath 
 * @returns {*[]} - list of objects containing the csv data
 */
function readCSVFile(filePath) {
	const csvData = fs.readFileSync(filePath, 'utf8');
	const parsedData = Papa.parse(csvData, { header: true });
	return parsedData.data;
}

/**
 * Convert the date string from ISO format string to short string.
 * @param {string} dateString 
 * @returns {string}
 */
function getDateFromString(dateString) {
	// Check if input string is valid
	if (!dateString || !dateString.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)) {
	  return null;
	}
	
	// Extract year, month, and date from input string
	const year = dateString.substring(0, 4);
	const month = dateString.substring(5, 7);
	const date = dateString.substring(8, 10);
	
	// Return formatted string
	return `${year}-${month}-${date}`;
}

module.exports = {
	shortStateName,
	formatString,
	formatPhoneNumber,
	formatCustomerRecords,
	createFullAddress,
	createFullName,
	getPlatform,
	recordError,
	saveAsJSON,
	aggregateCustomerHistory,
	mergeRecords,
	getPaymentType,
	removeFalseErrorRecords,
	convertTimestampToUTCFormat,
	getZipForCity,
	mergeCustomerRecordsByPhoneNumber,
	findDuplicateCustomerNumbers,
	customerInformationMissing,
	formatDate,
	readCSVFile,
	getDateFromString,
	removeSubsets
};