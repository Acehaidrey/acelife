const {TransactionRecord} = require("./record");
const utils = require("./utils");


const regexOrderType = 'Order placed.*\\b(DELIVERY|PICKUP)\\b';
const regexStoreName = '\\b(Aroma|Ameci)\\b';
const regexCustomerInfo = /(?:Customer:\s*)(.*?)(?:\n\n)/gs;
const regexCityStateZip = /^([\w\s]+),?\s([\w\s]+)\s(\d{5}(-\d{4})?)$/;
const regexCost = /TOTAL:\s*\$(\d+\.\d+)/;
const regexPaymentType = /Payment Method:\s*(\w+)/;


function createRecord(mail) {
	const record = new TransactionRecord(mail.date);
	// set the order type to PICKUP or DELIVERY
    if (mail.text.match(regexOrderType)) {
	    record.orderType = mail.text.match(regexOrderType)[1].toUpperCase();
    } else {
		utils.recordError(record, 'Order type not found.');
	}
	// set the store name to AMECI or AROMA
	if (mail.text.match(regexStoreName)) {
		record.storeName = mail.text.match(regexStoreName)[1].toUpperCase();
	} else {
		utils.recordError(record, 'Store name not found.');
	}
	// get the total amount
	if (mail.text.match(regexCost)) {
	  record.amount = parseFloat(mail.text.match(regexCost)[1]);
	} else {
	  utils.recordError(record, 'Cost info not matched.');
	}
	// get payment type
	if (mail.text.match(regexPaymentType)) {
	  record.paymentType = mail.text.match(regexPaymentType)[1].toUpperCase();
	} else {
	  utils.recordError(record, 'Payment type not matched.');
	}
    // clean string body and get the customer info block
	const cleanedText = mail.text
		.replaceAll('=0D', '')
		.replaceAll('=3D', '')
		.replaceAll('\r', '');
	// get the customer info block from the email block
	const customerInfoList = cleanedText.match(regexCustomerInfo);
	if (customerInfoList) {
		try {
			// split the string of customer info to further get name, number, address
			const customerInfo = customerInfoList[0].trim();
			const customerInfoArgs = customerInfo.replace('Customer:', '').split('\n');
			record.customerName = utils.formatString(customerInfoArgs[0].toUpperCase());  // customer name
			// if length not at least 2, error and return
			if (customerInfoArgs.length < 2) {
				utils.recordError(record, 'Customer info block < 2 lines. ' + customerInfoArgs);
				return record;
			}
			record.customerNumber = utils.formatPhoneNumber(customerInfoArgs[1]); // customer phone number
			// pickup expected length 2 (can be 4 by adding del info, delivery expected length 4
			if (
				(record.orderType === 'PICKUP' && customerInfoArgs.length < 2)
				|| (record.orderType === 'DELIVERY' && customerInfoArgs.length !== 4)
			) {
				utils.recordError(record, 'Order type does not match number args expected: ' + customerInfoArgs);
			}
			// if delivery, then get address info or if user passed in address info
			if (record.orderType === 'DELIVERY' || record.orderType >= 4) {
				const street = utils.formatString(customerInfoArgs[2].toUpperCase());
				const cityInfo = utils.formatString(customerInfoArgs[3].toUpperCase());
				const cityStZip = cityInfo.match(regexCityStateZip);
				record.street = street;
				record.customerAddress = street + ', ' + cityInfo;
				// cityStZip looks like (original address, city, state, zip, ...)
				if (cityStZip && cityStZip.length >= 4) {
					record.city = utils.formatString(cityStZip[1]);
					record.state = utils.formatString(utils.shortStateName(cityStZip[2]));
					record.zipcode = parseInt(utils.formatString(cityStZip[3]));
					record.customerAddress = record.street + ', ' + record.city + ', ' + record.state + ' ' + record.zipcode;
				} else {
					utils.recordError(record, 'cityStZip does not have enough inputs: ' + cityStZip);
				}
			}
		} catch {
			utils.recordError(record, 'Record threw exception')
		}
	} else {
		utils.recordError(record, 'customerInfoList null not match regex.')
	}
	// for errors add the original message text body too
	if (record.error) {
		record.mail = cleanedText;
	}
	return record;
}

module.exports = {createRecord}