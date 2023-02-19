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

const platformModules = {
  [Platform.SLICE]: require('./slice.js'),
  [Platform.DOORDASH]: require('./doordash.js'),
  [Platform.MENUSTAR]: require('./menustar.js'),
  [Platform.EATSTREET]: require('./eatstreet.js'),
  [Platform.GRUBHUB]: require('./grubhub.js'),
  [Platform.MENUFY]: require('./menufy.js')
};


function parseMboxFile(platform) {
	const messages = [];
	const transactionRecords = [];
	const transactionErrorRecords = [];
	const mbox = new Mbox();
	let messageCount = 0;
	mbox.on('message', function(msg) {
	  const mailparser = new MailParser({ streamAttachments : true });
	  mailparser.on('end', function(mail) {
		  messages.push(mail);
		  const record = getRecord(platform, mail, recordType.TRANSACTION);
		  transactionRecords.push(record);
		  if (record.error) {
			transactionErrorRecords.push(record);
		  }
	  	if (messages.length === messageCount) {
			const customerRecords = getRecord(platform, transactionRecords, recordType.CUSTOMER);
			console.log(transactionRecords);
			console.error(transactionErrorRecords);
			console.log(customerRecords);
			console.log(
				`Finished parsing ${messageCount} emails. ` +
				`Parsed ${transactionRecords.length} transaction records. ` +
				`${transactionErrorRecords.length} finished with errors. ` +
				`Parsed ${customerRecords.length} customer records.`
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

function getRecord(platform, obj, type = recordType.TRANSACTION) {
	/**
	 * Get the record depending on the type and make a call to the correct function needed.
	 * All platform modules in platformModules must define createTransactionRecord and createCustomerRecords.
	 */
    const module = platformModules[platform];
	if (!module) {
	    throw new Error(`Unsupported platform: ${platform}`);
	}
	return type === recordType.TRANSACTION ? module.createTransactionRecord(obj) : module.createCustomerRecords(obj);
}

function createJSONs(outputPath, transactionRecords, errorRecords, customerRecords) {
	/**
	 * Create the JSON files for the output of parsing the emails here from the mbox file.
	 * These JSONs are the transaction records, the error records from transactions,
	 * and the customer aggregated records.
	 */
	const outputPathSplit = outputPath.split('.')
	const errorPath = outputPathSplit[0] + '-errors.json'
	const customerPath = outputPathSplit[0] + '-customers.json'

	utils.saveAsJSON(outputPath, transactionRecords)
	utils.saveAsJSON(errorPath, errorRecords)
	utils.saveAsJSON(customerPath, customerRecords)
}

function main() {
	/**
	 * Entry point to the email parsing. Gets the platform from the input path and passes to parse files.
	 */
	const platform = utils.getPlatform(argv.i);
	console.log(`Parsing for platform: ${platform}`)
	parseMboxFile(platform);
}

main();
