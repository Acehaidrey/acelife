const fuzzy = require("fuzzball");
const fs = require("fs");
const {CustomerRecord} = require("./record");

function removeSimilarValues(list) {
	/**
	 * For names and addresses, users occasionally misspell the results.
	 * We want to filter out cases where there is this overlap. We identify
	 * records that have an 80% match (threshold below) from a list. We pick
	 * the first value for that match only to add. Uses edit distance to compare.
	 */
	const threshold = 80
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
			if (ratio > threshold) {
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

function saveAsJSON(outputPath, obj) {
	/**
	 * Helper function to save an object as a JSON.
	 */
	fs.writeFile(outputPath, JSON.stringify(obj), function(err) {
		if(err)
			return console.log(err);
	});
}

function aggregateCustomerHistory(records) {
	/**
	 * Takes the list of TransactionRecord and aggregates them. It creates a list of CustomerRecords.
	 * This assumes that the TransactionRecords are clean properly and won't have issues.
	 */
	const combinedRecords = {};
	for (const record of records) {
	  const key = `${record.storeName}-${record.customerNumber}`;
	  if (!combinedRecords[key]) {
		combinedRecords[key] = new CustomerRecord(record.storeName, record.customerNumber);
		combinedRecords[key].lastOrderDate = record.orderDate;
		combinedRecords[key].firstOrderDate = record.orderDate;
	  }
	  combinedRecords[key].customerNames.add(record.customerName);
	  combinedRecords[key].lastOrderDate = combinedRecords[key].lastOrderDate > record.orderDate ? combinedRecords[key].lastOrderDate : record.orderDate;
	  combinedRecords[key].firstOrderDate = combinedRecords[key].firstOrderDate < record.orderDate ? combinedRecords[key].firstOrderDate : record.orderDate;
	  combinedRecords[key].customerAddresses.add(record.customerAddress);
	  combinedRecords[key].customerEmails.add(record.customerEmail);
	  combinedRecords[key].orderCount += 1;
	  combinedRecords[key].totalSpend += record.amount;
	}

	const combinedRecordsArray = Object.values(combinedRecords);
	for (const record of combinedRecordsArray) {
		record.customerNames = removeSimilarValues(Array.from(record.customerNames));
		record.customerAddresses = removeSimilarValues(Array.from(record.customerAddresses).filter(function(val) { return val !== null; }));
		record.customerEmails = Array.from(record.customerEmails).filter(function(val) { return val !== null; });
		record.totalSpend = parseFloat(record.totalSpend.toFixed(2));
	}
	return combinedRecordsArray;
}


module.exports = {
	shortStateName,
	formatString,
	formatPhoneNumber,
	recordError,
	saveAsJSON,
	aggregateCustomerHistory
};