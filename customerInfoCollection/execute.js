#!/usr/bin/env node

const argv = require('yargs')
	.alias('n', 'numdays')
    .default('n', 1)
	.argv;

const os = require('os');
const fs = require('fs');
const path = require('path');
const childProcess = require('child_process');
const nodemailer = require('nodemailer');
const {Platform} = require("./constants");
const utils = require("./utils");

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
function sendEmail(outputPath, body) {
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
    const mailOptions = {
        from: senderEmail,
        to: recieveEmail,
        subject: 'Customer Export Execution',
        text: body,
        attachments: [
          {
            path: outputPath
          }
        ]
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
        return `echo "${filePath} | ${platform} had no command associated with it."`;
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
    let invokeCmd = `${cwd}/main.js -i ${filePath} -o ${fullOutputPath}`;

    if (platform === Platform.MENUFY) {
        // invokeCmd = `${cwd}/main.js -d ${deliveryfile} -e ${emailfile} -o ${fullOutputPath}`;
        invokeCmd = 'echo hi';
    }
    return invokeCmd;
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


function main() {
    let emailBody = logAndAppend('', `Running for date: ${nowString}`);
    const outputLogPath = path.join(logsPath, `output-${nowString}.log`);
    const outputs = [];
    const startTime = Date.now();

    try {
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
            emailBody = logAndAppend(emailBody, 'No google takeout zip found in the past day.')
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
    } catch {
        emailBody = logAndAppend(emailBody, 'Error executing main');
    } finally {
        const endTime = Date.now();
        const elapsedTime = (endTime - startTime) / 1000;
        emailBody = logAndAppend(emailBody, `Total Runtime: ${elapsedTime} secs.`);
        fs.writeFileSync(outputLogPath, emailBody + '\n' + outputs.join("\n"));
        sendEmail(outputLogPath, emailBody);
    }
}


// Build command to join together all the JSONs
// Filter for ameci and aroma separately and create jsons
// Export the files
// Fix the toast changes that were not saved
// Find BI tool to push the customer info to at end of it
// Attach the json files to the email
main();