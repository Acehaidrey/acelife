#!/usr/bin/env node

const MailParser = require('mailparser').MailParser;
const fs = require('fs');
const Mbox = require('node-mbox');
const os = require('os');
const path = require('path');
const Papa = require('papaparse');

// Get the home directory and Downloads
const homeDir = os.homedir();
const downloadsPath = path.join(homeDir, 'Downloads');
const outputPath = path.join(downloadsPath, 'inboxSenderCount.json');

const mboxFilePath = path.join(downloadsPath, 'Inbox-001.mbox');
const senders = {};

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

function GetSenderStatsForEmailsInInbox() {
    const startTime = Date.now();
    const mbox = new Mbox(fs.createReadStream(mboxFilePath));
    mbox.on('message', function(msg) {
      const mailParser = new MailParser();
      mailParser.on('headers', function(headers) {
        // console.log(headers.from)
        if (headers.from && headers.from.length > 0) {
          const sender = headers.from;
          senders[sender] = (senders[sender] || 0) + 1;
        }
      });
      mailParser.write(msg);
      mailParser.end();
    });
    
    mbox.on('end', function() {
      const p = 
      saveAsJSON(outputPath, senders);
      const endTime = Date.now();
      const elapsedTime = (endTime - startTime) / 1000;
      console.log(`Took ${elapsedTime} seconds to run analysis.`)
      console.log(senders);
      const fp = fs.readFileSync(filepath);
      records = JSON.parse(fp);
    });
    
}

// Check mbox files to see which to delete
GetSenderStatsForEmailsInInbox()

// Read JSON file
const data = JSON.parse(fs.readFileSync(outputPath));

// Sort the object by value in descending order
const sortedData = Object.fromEntries(Object.entries(data).sort((a, b) => b[1] - a[1]));

// Print sorted object
// console.log(sortedData);

// Print top 50 items from the sorted object
for (const [email, count] of Object.entries(sortedData).slice(0, 250)) {
    console.log(`${email}: ${count}`);
}