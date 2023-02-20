const fuzzy = require("fuzzball");
const fs = require("fs");
const path = require('path');
const {CustomerRecord, TransactionRecord} = require("./record");
const {SIMILARITY_THRESHOLD, keyType, paymentType, Platform} = require("./constants");

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
	return parseInt(phoneNumber.trim().replace('1(', '(').replace(/\D/g, ''));
}

/**
 * Given all the separated address info, create one formatted address string.
 * @param {string|null} street
 * @param {string|null} city
 * @param {string|null} state
 * @param {string|int} zip
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
 * @returns {string}
 */
function createFullName(firstName, lastName) {
	let fullName = '';
	if (firstName !== null && firstName !== undefined) {
		fullName = firstName.toUpperCase() + ' ';
	}
	if (lastName !== null && lastName !== undefined) {
		fullName += lastName.toUpperCase();
	}
	return fullName.trim();
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
	const combinedRecords = {};
	for (const record of records) {
	  const keyIdent = keyIdentifier === keyType.NAME ? record.customerName : record.customerNumber;
	  const key = `${record.storeName}-${keyIdent}`;

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
	let partner = inputPath.match(/([^/]+)\.mbox$/);
	if (partner) {
		partner = partner[1];
		if (partner.startsWith('Orders-')) {
			partner = partner.replace(/^Orders-/, '');
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
		record.customerNames = removeSimilarValues(Array.from(record.customerNames));
		record.customerAddresses = removeSimilarValues(Array.from(record.customerAddresses).filter(function(val) { return val !== null; }));
		record.customerEmails = Array.from(record.customerEmails).filter(function(val) { return val !== null; });
		record.platforms = Array.from(record.platforms).filter(function(val) { return val !== null; });
		record.totalSpend = parseFloat(record.totalSpend.toFixed(2));
	}
	return records;
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

/***
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
	getPaymentType
};