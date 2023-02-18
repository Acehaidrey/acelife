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
const slice = require("./slice.js")


function parseMboxFile() {
	const messages = [];
	const records = [];
	const errors = [];
	const mbox = new Mbox();
	let messageCount = 0;
	mbox.on('message', function(msg) {
	  // parse message using MailParser
	  const mailparser = new MailParser({ streamAttachments : true });
	  mailparser.on('end', function(mail) {
		  messages.push(mail);
		  // createRecord will be different based on the partner
		  const record = slice.createRecord(mail);
		  records.push(record);
		  if (record.error) {
			errors.push(record);
		  }
	  	if (messages.length === messageCount) {
			const summarized = utils.aggregateCustomerHistory(records);
			console.log('Finished parsing messages: ', messageCount);
			console.log('Finished with errors: ', errors.length);
			console.log('Finished with aggregated: ', summarized.length);
	  		if (argv.o) {
			  createJSONs(argv.o, records, errors, summarized);
			}
	  		else {
			  console.log(records);
			  console.error(errors);
			  console.error(summarized);
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

function createJSONs(outputPath, transactionRecords, errorRecords, customerRecords) {
	const outputPathSplit = outputPath.split('.')
	const errorPath = outputPathSplit[0] + '-errors.' + outputPathSplit[1]
	const customerPath = outputPathSplit[0] + '-customers.' + outputPathSplit[1]

	utils.saveAsJSON(outputPath, transactionRecords)
	utils.saveAsJSON(errorPath, errorRecords)
	utils.saveAsJSON(customerPath, customerRecords)
}

parseMboxFile();
// parse the grubhub
// parse the menustar
// parse eatstreet
// parse doordash
// parse the menufys
