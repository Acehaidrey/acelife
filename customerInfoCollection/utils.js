const fuzzy = require("fuzzball");
const fs = require("fs");
const path = require('path');
const {CustomerRecord} = require("./record");
const {SIMILARITY_THRESHOLD, keyType} = require("./constants");

function removeSimilarValues(list) {
	/**
	 * For names and addresses, users occasionally misspell the results.
	 * We want to filter out cases where there is this overlap. We identify
	 * records that have an 80% match (threshold below) from a list. We pick
	 * the first value for that match only to add. Uses edit distance to compare.
	 */
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

function shortStateName(stateName) {
	/**
	 * Convert the state name to the short name. Our orders should all be in CA so.
	 */
	stateName = stateName.toUpperCase();
	if (stateName === 'CALIFORNIA') {
		return 'CA';
	}
	return stateName;
}

function recordError(record, errorMsg) {
    /**
     * Record an error message and mark the record had an error parsing the record.
     */
	record.error = true;
	record.errorReason.push(errorMsg);
}

function formatString(str) {
	/**
	 * Cleans a string to replace non-ascii characters and removes \r from the string.
	 * Removes multiple white spaces to put just one. Trims the string.
	 */
	if (str === null || str === undefined || !str) {
		return str;
	}
	return str.replaceAll('=0D', '')
		.replaceAll('=3D', '')
		.replaceAll('\r', '')
		.replace(/\s+/g,' ')
		.trim();
}

function formatPhoneNumber(phoneNumber) {
	/**
	 * Cleans a string to replace non-ascii characters and removes \r from the string.
	 * Removes multiple white spaces to put just one. Trims the string.
	 */
	if (phoneNumber === null || phoneNumber === undefined) {
		return phoneNumber;
	}
	return parseInt(phoneNumber.trim().replace('1(', '(').replace(/\D/g, ''));
}

function createFullAddress(street, city, state, zip) {
	/**
	 * Given all the separated address info, create one formatted address string.
	 */
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

function createFullName(firstName, lastName) {
	/**
	 * Given all the separated address info, create one formatted address string.
	 */
	let fullName = '';
	if (firstName !== null && firstName !== undefined) {
		fullName = firstName.toUpperCase() + ' ';
	}
	if (lastName !== null && lastName !== undefined) {
		fullName += lastName.toUpperCase();
	}
	return fullName.trim();
}

function saveAsJSON(outputPath, obj) {
	/**
	 * Helper function to save an object as a JSON.
	 */
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

function aggregateCustomerHistory(records, keyIdentifier = keyType.PHONE) {
	/**
	 * Takes the list of TransactionRecord and aggregates them. It creates a list of CustomerRecords.
	 * This assumes that the TransactionRecords are clean properly and won't have issues.
	 */
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
	  combinedRecords[key].totalSpend += record.amount;
	}
	return formatCustomerRecords(Object.values(combinedRecords));
}

function getPlatform(inputPath) {
	/**
	 * Get the platform name from the input paths of the mbox files.
	 */
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

function formatCustomerRecords(records) {
	/**
	 * Format customer records sets into lists and remove similar values, round the values to two decimal places.
	 */
	for (const record of records) {
		record.customerNames = removeSimilarValues(Array.from(record.customerNames));
		record.customerAddresses = removeSimilarValues(Array.from(record.customerAddresses).filter(function(val) { return val !== null; }));
		record.customerEmails = Array.from(record.customerEmails).filter(function(val) { return val !== null; });
		record.platforms = Array.from(record.platforms).filter(function(val) { return val !== null; });
		record.totalSpend = parseFloat(record.totalSpend.toFixed(2));
	}
	return records;
}

module.exports = {
	removeSimilarValues,
	shortStateName,
	formatString,
	formatPhoneNumber,
	formatCustomerRecords,
	createFullAddress,
	createFullName,
	getPlatform,
	recordError,
	saveAsJSON,
	aggregateCustomerHistory
};