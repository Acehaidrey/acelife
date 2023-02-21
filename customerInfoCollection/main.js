#!/usr/bin/env node

const MailParser = require('mailparser').MailParser;
const fs = require('fs');
const Mbox = require('node-mbox');
const argv = require('yargs')
	.alias('i', 'input')
	.alias('o', 'output')
	.demand(['i'])
	.argv;

const utils = require("./utils.js");
const {Platform, recordType} = require("./constants");
const {TransactionRecord, CustomerRecord} = require("./record");

const platformModules = {
  [Platform.SLICE]: require('./slice.js'),
  [Platform.DOORDASH]: require('./doordash.js'),
  [Platform.MENUSTAR]: require('./menustar.js'),
  [Platform.EATSTREET]: require('./eatstreet.js'),
  [Platform.GRUBHUB]: require('./grubhub.js'),
  [Platform.BRYGID]: require('./brygid.js'),
  // [Platform.MENUFY]: require('./menufy.js')
};

/**
 * A function to read the mail in the mbox file and parse it specific to the platform
 * to create transaction records and customer records.
 * @param {Platform} platform - Platform type
 */
function parseMboxFile(platform) {
	const messages = [];
	let transactionRecords = [];
	let transactionErrorRecords = [];
	const mbox = new Mbox();
	let messageCount = 0;
	mbox.on('message', function(msg) {
	  const mailparser = new MailParser({ streamAttachments : true });
	  mailparser.on('end', function(mail) {
		  messages.push(mail);
		  const record = getRecord(platform, mail, recordType.TRANSACTION);
		  if (record.error) {
			transactionErrorRecords.push(record);
		  } else {
			transactionRecords.push(record);
		  }
	  	if (messages.length === messageCount) {
			const originalTransactionLength = transactionRecords.length;
			const originalErrorLength = transactionErrorRecords.length;
			// merge transaction records based on orderId
			transactionRecords = utils.mergeRecords(transactionRecords);
			transactionErrorRecords = utils.removeFalseErrorRecords(transactionRecords, transactionErrorRecords);
			const customerRecords = getRecord(platform, transactionRecords, recordType.CUSTOMER);
			// console.log(transactionRecords);
			// console.error(transactionErrorRecords);
			// console.log(customerRecords);
			console.log(
				`${messageCount} parsed emails.\n` +
				`${originalTransactionLength} parsed transaction records.\n` +
				`${originalErrorLength} finished with errors.\n` +
				`${transactionErrorRecords.length} finished with errors after merging orderIds.\n` +
				`${transactionRecords.length} transaction records after merging orderIds.\n` +
				`${customerRecords.length} parsed customer records.`
			);
	  		if (argv.o) {
			  createJSONs(argv.o, transactionRecords, transactionErrorRecords, customerRecords);
			}
	  	}
	  });
	  mailparser.write(msg);
	  mailparser.end();
	});

	mbox.on('end', function(parsedCount) {
		console.log('Completed Parsing mbox File.');
		messageCount = parsedCount;
	});

	if (fs.existsSync(argv.input)) {
		const handle = fs.createReadStream(argv.input);
		//handle.setEncoding('ascii');
		handle.pipe(mbox);
	}
}

/**
 * Get the record depending on the type and make a call to the correct function needed.
 * All platform modules in platformModules must define createTransactionRecord and createCustomerRecords.
 * @param {Platform} platform
 * @param {TransactionRecord|CustomerRecord[]} obj
 * @param {recordType} type
 * @returns {TransactionRecord|CustomerRecord[]}
 */
function getRecord(platform, obj, type = recordType.TRANSACTION) {
    const module = platformModules[platform];
	if (!module) {
	    throw new Error(`Unsupported platform: ${platform}`);
	}
	return type === recordType.TRANSACTION ? module.createTransactionRecord(obj) : module.createCustomerRecords(obj);
}

/**
 * Create the JSON files for the output of parsing the emails here from the mbox file.
 * These JSONs are the transaction records, the error records from transactions,
 * and the customer aggregated records.
 * @param {string} outputPath
 * @param {TransactionRecord[]} transactionRecords
 * @param {TransactionRecord[]} errorRecords
 * @param {CustomerRecord[]} customerRecords
 */
function createJSONs(outputPath, transactionRecords, errorRecords, customerRecords) {
	const outputPathSplit = outputPath.split('.')
	const errorPath = outputPathSplit[0] + '-errors.json'
	const customerPath = outputPathSplit[0] + '-customers.json'

	utils.saveAsJSON(outputPath, transactionRecords)
	utils.saveAsJSON(errorPath, errorRecords)
	utils.saveAsJSON(customerPath, customerRecords)
}

/**
 * Entry point to the email parsing. Gets the platform from the input path and passes to parse files.
 */
function main() {
	const platform = utils.getPlatform(argv.i);
	console.log(`Parsing for platform: ${platform}`)
	parseMboxFile(platform);
}

main();
