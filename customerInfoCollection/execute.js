#!/usr/bin/env node

const argv = require('yargs')
	.alias('n', 'numdays')
    .default('n', 1)
	.argv;

const Papa = require('papaparse');
const os = require('os');
const fs = require('fs');
const path = require('path');
const childProcess = require('child_process');
const nodemailer = require('nodemailer');
const {Platform, recordType, storeType, States} = require("./constants");
const utils = require("./utils");
const { CustomerRecord } = require('./record');

// Get the current time and the time from 1 day ago
const now = new Date();
const daysAgo = new Date(now - 24 * 60 * 60 * 1000 * argv.n);
const nowString = utils.formatDate(now);

// Get the home directory and the current working directory
const cwd = process.cwd();
const homeDir = os.homedir();

// Define the paths to the downloads folder and the destination folder
const downloadsPath = path.join(homeDir, 'Downloads');
const reportsPath = path.join(cwd, 'Reports');
const logsPath = path.join(reportsPath, 'log');
const posPath = path.join(reportsPath, 'POS');
const outputPath = path.join(reportsPath, 'Output');
const outputTodayPath =  path.join(outputPath, nowString);

// Define the pattern for matching zip files
const zipPattern = /^takeout-.*\.zip$/;

// Constants for email
const senderEmail = 'acehaidrey@gmail.com';
const recieveEmail = senderEmail;
const emailPassword = process.env.EMAIL_PASSWORD;

/**
 * Sending an email utility.
 * @param {string} outputPath - path of file to attach to email
 * @param {string} body  - email body content
 */
function sendEmail(fileAttachments, body) {
    // Send an email with the output file attached
    const transporter = nodemailer.createTransport({
        host: 'smtp.gmail.com',
        port: 587,
        auth: {
            user: senderEmail,
            pass: emailPassword
        }
    });
    // Setup mail options
    const emailAttachments = [];
    for (const output of fileAttachments) {
        emailAttachments.push({path: output});
    }

    const mailOptions = {
        from: senderEmail,
        to: recieveEmail,
        subject: 'Customer Export Execution',
        text: body,
        attachments: emailAttachments
    };
    // Send email if password
    if (emailPassword) {
        transporter.sendMail(mailOptions, function(error, info) {
            if (error) {
              console.log(error);
            } else {
              console.log('Email sent: ' + info.response);
            }
          });
    } else {
        console.log(`No email password found: ${emailPassword}. Properly set env var EMAIL_PASSWORD.`)
    }
}

/**
 * Create the MBOX file processing command based on the platform.
 * @param {string} filePath 
 * @param {Platform} platform 
 * @returns {string}
 */
function createMboxProcessingCommand(filePath, platform) {
    if (!Platform.hasOwnProperty(platform)) {
        return `echo "Parsing for platform: ${platform}\n.${filePath} | ${platform} had no command associated with it."`;
    }
    const fullOutputPath = path.join(outputTodayPath, platform.toLowerCase());
    if (platform === Platform.BRYGID) {
        filePath = getLatestFileForPlatform(Platform.BRYGID);
    }
    if (platform === Platform.SPEEDLINE) {
        filePath = getLatestFileForPlatform(Platform.SPEEDLINE);
    }
    if (platform === Platform.TOAST) {
        // change to add a -e flag with csv file
        filePath = getLatestFileForPlatform(Platform.TOAST);
    }
    return `${cwd}/main.js -i ${filePath} -o ${fullOutputPath}`;
}

/**
 * Get the latest customer export file in the folder.
 * @param {Platform} platform 
 * @returns {string} - filename of the latest file given the platform.
 */
function getLatestFileForPlatform(platform) {
    const directory = posPath;
    const platformPrefix = `${platform}-`;
    const fileExtension = 'csv';
    const files = fs.readdirSync(directory)
      .filter(file => file.toUpperCase().startsWith(platformPrefix) && file.endsWith(fileExtension))
      .map(file => ({ path: path.join(directory, file), mtime: fs.statSync(path.join(directory, file)).mtime }))
      .sort((a, b) => b.mtime.getTime() - a.mtime.getTime());
    return files.length > 0 ? files[0].path : null;
}

/**
 * Both append to the email body and log to console
 * @param {string} text - email body to append to
 * @param {string} msg - message to be appended
 * @returns {string} new email body text
 */
function logAndAppend(text, msg) {
	text += '\n' + msg;
	console.log(msg);
	return text;
}

/**
 * Clean up log files beyond 30 days.
 */
function cleanupOldLogs() {    
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    
    fs.readdir(logsPath, (err, files) => {
      if (err) throw err;
    
      files.forEach(file => {
        const filePath = path.join(logsPath, file);
        const stats = fs.statSync(filePath);
        const fileAgeInMs = Date.now() - stats.mtime.getTime();
    
        if (fileAgeInMs > thirtyDaysAgo) {
          fs.unlinkSync(filePath);
          console.log(`Deleted log file: ${filePath}`);
        }
      });
    });
}

/**
 * Convert the JSON file to the CSV. We unpack the email so that each unique email and phone number will have a row.
 * @param {string} filepath 
 * @returns {string} - csv filepath written
 */
function convertCustomerJSONtoCSV(filepath, records) {
    // Read JSON data from file
    if (!records) {
        const fp = fs.readFileSync(filepath);
        records = JSON.parse(fp);
        console.log(filepath, fp, records.length)
    }
    // Assume the variable `records` contains the list of records
    const newRecords = [];
    records.forEach(record => {
        // If the original record had an empty `customerEmails` array,
        // add a new record with an empty `customerEmails` array
        if (record.customerEmails.length === 0) {
            const newRecord = {
                platforms: record.platforms.join(';'),
                storeName: record.storeName,
                customerNumber: record.customerNumber,
                customerNames: record.customerNames.join(';'),
                customerAddresses: record.customerAddresses.join(';'),
                customerEmails: null,
                lastOrderDate: utils.getDateFromString(record.lastOrderDate),
                firstOrderDate: utils.getDateFromString(record.firstOrderDate),
                orderCount: record.orderCount,
                totalSpend: record.totalSpend
            };
            newRecords.push(newRecord);
        } else {
            record.customerEmails.forEach(email => {
                // Create a new record with the same values as the original record,
                // but with the `customerEmails` field set to an array with just `email`
                const newRecord = {
                platforms: record.platforms.join(';'),
                storeName: record.storeName,
                customerNumber: record.customerNumber,
                customerNames: record.customerNames.join(';'),
                customerAddresses: record.customerAddresses.join(';'),
                customerEmails: email,
                lastOrderDate: utils.getDateFromString(record.lastOrderDate),
                firstOrderDate: utils.getDateFromString(record.firstOrderDate),
                orderCount: record.orderCount,
                totalSpend: record.totalSpend
                };
                // Add the new record to the list of new records
                newRecords.push(newRecord);
            });
        }
    });
    // convert data to CSV format
    const csv = Papa.unparse(newRecords);
    // write CSV data to file
    const csvFilePath = filepath.replace('.json', '.csv');
    fs.writeFileSync(csvFilePath, csv);
    return csvFilePath;
}

/**
 * Finds all json files of matching the extension type and then creates a kv pair of platform: json objects list.
 * @param {string} directoryPath 
 * @param {recordType} extType 
 * @returns {[CustomerRecord[]]}
 */
function readJSONOutputs(directoryPath, extType = recordType.CUSTOMER) {
    const jsons = {};
    const files = fs.readdirSync(directoryPath);
    const extTypeFiles = files.filter(file => file.endsWith('-' + extType.toLowerCase() + '.json'));
    extTypeFiles.map(file => {
        const filePath = path.join(directoryPath, file);
        const fileContent = fs.readFileSync(filePath);
        const jsonContent = JSON.parse(fileContent);
        jsons[file.toUpperCase().replace(`-${extType}.JSON`, '')] = jsonContent;
    });
    return jsons;
}

function main() {
    let emailBody = logAndAppend('', `Running for date: ${nowString}`);
    const outputLogPath = path.join(logsPath, `output-${nowString}.log`);
    const outputs = [];
    const startTime = Date.now();
    let finalState = States.NOT_RUN;
    let AllCustomersFilePath = path.join(outputTodayPath, 'AllCustomers.json');
    let AmeciFilePath = path.join(outputTodayPath, 'AmeciCustomers.json');
    let AromaFilePath = path.join(outputTodayPath, 'AromaCustomers.json');

    try {
        // Clean up log files created by these processes
        cleanupOldLogs();
        // Get a list of files in the downloads folder
        const files = fs.readdirSync(downloadsPath);
        // Check if the directories exists or create it
        for (const path of [reportsPath, logsPath, posPath, outputPath, outputTodayPath]) {
            if (!fs.existsSync(path)) {
                fs.mkdirSync(path);
            }
        }
        // Find the files that match the zip file pattern and were modified in the last n days
        const matchingFiles = files.filter(file => {
            const filePath = path.join(downloadsPath, file);
            const stats = fs.statSync(filePath);
            return zipPattern.test(file) && stats.mtime > daysAgo;
        });
        if (!matchingFiles || matchingFiles.length < 1) {
            emailBody = logAndAppend(emailBody, 'No google takeout zip found in the past day.');
            return;
        }
        console.log('Matching files: ' + matchingFiles);
        // Unzip the matching files and move them to the reports folder
        const matchFilesList = [];
        matchingFiles.forEach(file => {
            const filePath = path.join(downloadsPath, file);
            const destPath = path.join(reportsPath, file.replace(/\.zip$/, ''));
            matchFilesList.push(destPath);
            const cmd = `unzip -o ${filePath} -d ${destPath}`;
            childProcess.execSync(cmd);
            emailBody = 'Please see attached report.\nFound zip file: ' + file;
            emailBody = logAndAppend(emailBody, 'Running: ' + cmd);
        });
        // Run some commands and save the output to a file
        for (const zipDir of matchFilesList) {
            const mboxFiles = fs.readdirSync(path.join(zipDir, 'Takeout', 'Mail')); // google takeout format
            for (const mboxFile of mboxFiles) {
                const fullPath = path.join(zipDir, 'Takeout', 'Mail', mboxFile);
                const platform = utils.getPlatform(mboxFile);
                emailBody = logAndAppend(emailBody, `Output file: ${fullPath}. Platform identified: ${platform}.`);
                if (mboxFile.endsWith('.mbox') && platform) {
                    mboxCmd = createMboxProcessingCommand(fullPath, platform);
                    emailBody = logAndAppend(emailBody, 'Running: ' + mboxCmd);
                    try {
                        const output = childProcess.execSync(mboxCmd).toString();
                        outputs.push(output);
                        emailBody = logAndAppend(emailBody, output);
                    } catch {
                        emailBody = logAndAppend(emailBody, 'Error executing command: ' + mboxCmd);
                    }
                }
            }
        }
        // Combine the outputs to a single json for all customers
        jsons = readJSONOutputs(outputTodayPath);
        let combinedJson = [];
        for (const key in jsons) {
            emailBody = logAndAppend(emailBody, `JSON: ${key}, Number of Records: ${jsons[key].length}`);
            combinedJson.push(...jsons[key]);
        }
        emailBody = logAndAppend(emailBody, `Combined JSON Number of Records BEFORE Merge: ${combinedJson.length}`);
        combinedJson = utils.mergeCustomerRecordsByPhoneNumber(combinedJson);
        emailBody = logAndAppend(emailBody, `Combined JSON Number of Records AFTER Merge: ${combinedJson.length}`);
        // ameci handling
        const AmeciCustomers = combinedJson.filter((record) => record.storeName === storeType.AMECI);
        emailBody = logAndAppend(emailBody, `Number of Ameci Customers: ${AmeciCustomers.length}`);
        // aroma handling
        const AromaCustomers = combinedJson.filter((record) => record.storeName === storeType.AROMA);
        emailBody = logAndAppend(emailBody, `Number of Aroma Customers: ${AromaCustomers.length}`);
        // write all files out in json and in csv
        utils.saveAsJSON(AllCustomersFilePath, combinedJson);
        utils.saveAsJSON(AmeciFilePath, AmeciCustomers);
        utils.saveAsJSON(AromaFilePath, AromaCustomers);
        AllCustomersFilePath = convertCustomerJSONtoCSV(AllCustomersFilePath, combinedJson);
        AmeciFilePath = convertCustomerJSONtoCSV(AmeciFilePath, AmeciCustomers);
        AromaFilePath = convertCustomerJSONtoCSV(AromaFilePath, AromaCustomers);
        emailBody = logAndAppend(emailBody, `Created JSON and CSV Files:\n${AllCustomersFilePath}\n${AmeciFilePath}\n${AromaFilePath}`);
        finalState = States.SUCCESS;
    } catch (error) {
        emailBody = logAndAppend(emailBody, 'Error executing main because:\n' + error.stack);
        finalState = States.FAILED;
    } finally {
        const endTime = Date.now();
        const elapsedTime = (endTime - startTime) / 1000;
        emailBody = logAndAppend(emailBody, `Total Runtime: ${elapsedTime} secs.\nFinal State: ${finalState}`);
        fs.writeFileSync(outputLogPath, emailBody + '\n' + outputs.join('\n'));
        const attachFiles = [outputLogPath, AmeciFilePath, AromaFilePath].filter((file) => fs.existsSync(file));
        emailBody = logAndAppend(emailBody, `Adding following attachments to send as part of email: ${attachFiles}.`);
        sendEmail(attachFiles, emailBody);
    }
}

// Fix the toast changes that were not saved
// Find BI tool to push the customer info to at end of it
main();