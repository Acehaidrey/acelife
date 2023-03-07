const uberContestLabel = 'Billings/UberEats/Adjustments';
const driveFolderNameUE = 'UberEatsAdjustments';
const uberSenderEmail =  'restaurants@uber.com';
const futureFoodsEmail = 'support@futurefoods.io';

const daysAgoCutoffForContestUber = 7;
const nonFutureFoodsRestaurants = ['Aroma Pizza', 'The Wing Stop', 'Trattoria Contadina', 'Ameci Pizza & Pasta - Lake Forest'];

/** Helper Functions */

/**
 * For the part of the email where the row goes over a single line limit, we want to combine the line
 * so that each line is one adjustment record. We split by looking for rows matching 2/18/23 - 19:00 format 
 * and if it does not, then it is a continuation of the previous line.
 * For example:
 * const arr = [
 *     '2/18/23 - 19:00 A1634 $ 0.00 ($ 5.38) 2 Liter Soda|Garlic Cheese Sticks Entire ,',
 *     'order incorrect,',
 * ]    ==>
 * const arr = ['2/18/23 - 19:00 A1634 $ 0.00 ($ 5.38) 2 Liter Soda|Garlic Cheese Sticks Entire order incorrect']
 * @param {*[]} arr 
 * @returns {*[]} 
 */
function mergeNonMatchingRows(arr) {
    const mergedArr = [];
    let currentRow = "";
    
    for (const row of arr) {
      if (/^\d{1,2}\/\d{1,2}\/\d{2}\s-\s\d{1,2}:\d{2}/.test(row)) {
        if (currentRow) {
          mergedArr.push(currentRow);
          currentRow = "";
        }
        mergedArr.push(row);
      } else {
        currentRow += " " + row;
      }
    }
    if (currentRow) {
      mergedArr.push(currentRow.trim());
    }
    return mergedArr;
}

/**
 * Finds the last row matching 2/18/23 - 19:00 format as from email specifics that will
 * be the last data row for adjustments.
 * @param {*[]} input 
 * @returns {int}
 */
function findLastDateTimeIndex(input) {
    var dateTimeRegex = /\d{1,2}\/\d{1,2}\/\d{2}\s-\s\d{1,2}:\d{2}/g;
    var lastMatchIndex = -1;
    
    for (var i = 0; i < input.length; i++) {
      var row = input[i];
      var matches = row.match(dateTimeRegex);
      
      if (matches !== null && matches.length > 0) {
        lastMatchIndex = i;
      }
    }
    return lastMatchIndex;
  }

/**
 * Parses the adjustment row record that look like:
 *     '2/18/23 - 19:00 A1634 $ 0.00 ($ 5.38) 2 Liter Soda|Garlic Cheese Sticks Entire order incorrect'
 * Takes in the information here to build the record of information to use for formatting email to send later on.
 * @param {*} row {*}
 * @param {string} restaurant
 * @param {string} address
 * @returns {obj|null}
 */
function parseRow(row, restaurant, address) {
    var regex = /^(\d{1,2}\/\d{1,2}\/\d{2,4}\s-\s\d{1,2}:\d{1,2})\s+(\w+)\s+(\$\s?\d+\.\d{2})\s+\((\$?\s?\d+\.\d{2})\)\s+(.+)$/;
    var matches = row.match(regex);
    if (matches) {
        var date = new Date(matches[1].replace('-', ' '));
        var orderId = matches[2];
        var orderAmt = matches[3].replace(' ', '');
        var adjAmt = matches[4].replace(' ', '');
        var reason = matches[5];
        return {
            ID: orderId,
            Type: 'adjustment',
            Date: date,
            Total: orderAmt,
            Adjustment: adjAmt,
            Reason: reason,
            Restaurant: restaurant,
            Address: address + ', Lake Forest, CA 92630',
            Provider: 'UberEats'
        };
    }
    return null;
}

/**
 * Delete files older than 30 days in the Drive location we copy PDFs to.
 */
function deleteOldFilesInDrive(deleteDaysAgo = 30) {
    // Set the ID of the folder you want to delete files from
    const driveFolder = DriveApp.getFoldersByName(driveFolderNameUE).next();
    // Get the folder
    const folder = DriveApp.getFolderById(driveFolder.getId());
    // Calculate the date 30 days ago
    const thirtyDaysAgo = new Date(Date.now()  - deleteDaysAgo * 24 * 60 * 60 * 1000);
    // Get all files in the folder
    const files = folder.getFiles();
    // Loop through each file
    while (files.hasNext()) {
      const file = files.next();
      // Check if the file was last modified more than 30 days ago
      if (file.getLastUpdated() < thirtyDaysAgo) {
        // Delete the file
        file.setTrashed(true);
      }
    }
}

/**
 * Parse the email PDF converted text file and get the relevant information for contesting information.
 * @param {string} emailBody 
 * @returns {*[]}
 */
function createEmailContext(emailBody) {
    let seenError = false;
    const disputeRecords = [];
    const emailBodyList = emailBody.split('\n').map((value) => value.trim()).filter(row => row.length > 0);
    const restaurant = emailBodyList[2];
    if (!restaurant) {
        seenError = true;
        Logger.log('No restaurant found in the email.');
    }
    // if restaurant name has ameci then use ameci address, otherwise always aroma
    const address = restaurant.toLowerCase().includes('ameci') ? '25431 Trabuco Road' : '20491 Alton Parkway';
    if (!address) {
        seenError = true;
        Logger.log('No address found in the email.');
    }
    // find where Total Order Error Adjustments is in the output then get all values after it until end search string
    const startSearchIndex = emailBodyList.findIndex(function(str) {
        return str.toLowerCase().includes('Total Order Error Adjustments'.toLowerCase());
    });
    if (startSearchIndex === -1) {
        seenError = true;
        Logger.log('Total Order Error Adjustments not found in email.');
    }
    // this is hardcoded currently as the format but we cannot rely on this - instead use logic that we get
    // the adjusted orders number of records, and do some manual calculation to add this many rows the check
    // if that section does not exist we will try to find last error row and set that as the end
    let endSearchIndex = findLastDateTimeIndex(emailBodyList) + 1;
    if (endSearchIndex === -1) {
        Logger.log('Could not find the last date time index.');
        endSearchIndex = emailBodyList.findIndex(function(str) {
            return str.toLowerCase().includes('A new way to see your financial information'.toLowerCase());
        });
    };
    if (endSearchIndex === -1) {
        seenError = true;
        Logger.log('Could not find A new way to see your financial information in the email.');
    }
    const adjustmentInfoSubArray = emailBodyList.slice(startSearchIndex + 1, endSearchIndex);
    // combine the record of the headers from 2 -> 1 row if its separated (could change)
    for (var i = 0; i < adjustmentInfoSubArray.length - 1; i++) {
        var row1 = adjustmentInfoSubArray[i];
        var row2 = adjustmentInfoSubArray[i+1];
        if (row1.includes("ADJUSTMENT") && row2.includes("ERROR TYPE")) {
          var combinedRow = row1 + " " + row2;
          adjustmentInfoSubArray.splice(i, 2, combinedRow);
          i--;
        }
    }
    const numAdjustedOrders = parseInt(adjustmentInfoSubArray[adjustmentInfoSubArray.indexOf('ADJUSTED ORDERS') + 1]);
    if (!numAdjustedOrders) {
        seenError = true;
        Logger.log('Could not parse numAdjustedOrders in email.')
    }
    let totalAdjustedOrders = adjustmentInfoSubArray[adjustmentInfoSubArray.indexOf('TOTAL ADJUSTMENTS') + 1];
    totalAdjustedOrders = parseFloat(totalAdjustedOrders.match(/([0-9]+\.[0-9]+)/)[0]);
    if (!totalAdjustedOrders) {
        seenError = true;
        Logger.log('Could not parse totalAdjustedOrders in email.')
    }
    const headerIndex = adjustmentInfoSubArray.findIndex(function(str) {
        return str.toUpperCase().includes('TOTAL ADJUSTMENT'.toUpperCase()) && str.toUpperCase().includes('ERROR TYPE'.toUpperCase());
    });
    if (headerIndex === -1) {
        seenError = true;
        Logger.log('Could not parse headerIndex in email.')
    }
    let dataRows = adjustmentInfoSubArray.slice(headerIndex + 1);
    dataRows = mergeNonMatchingRows(dataRows).filter(Boolean);
    for (var i = 0; i < dataRows.length; i++) {
        const record = parseRow(dataRows[i], restaurant, address);
        if (record !== null) {
            disputeRecords.push(record);
        }
    }
    // check if the adjustment count for records vs top level differ
    if (disputeRecords.length !== numAdjustedOrders) {
        seenError = true;
        Logger.info(`Number of adjustments differs: len dispute records: ${disputeRecords.length}, count in email: ${numAdjustedOrders}`)
    }
    const totalAdjustment = disputeRecords.reduce((total, record) => total + parseFloat(record.Adjustment.replace('$', '')), 0);
    if (totalAdjustment.toFixed(2) !== totalAdjustedOrders.toFixed(2)) {
        seenError = true;
        Logger.info(`Amount of adjustments differs: sum dispute records: ${totalAdjustment}, sum in email: ${totalAdjustedOrders}`)
    }

    return {
        'records': disputeRecords,
        'error': seenError,
        'adjustmentCount': numAdjustedOrders,
        'adjustmentSum': totalAdjustedOrders
    }
}

/**
 * Get random font type that looks like handwriting signature somewhat.
 * @returns {string}
 */
function getRandomSignatureFont() {
    const fonts = ['Dancing Script', 'Pacifico', 'Great Vibes', 'Alex Brush', 'Allura'];
    const randomIndex = Math.floor(Math.random() * fonts.length);
    return fonts[randomIndex];
}

/**
 * Get random name generated from a list of common first names and last names.
 * @returns {string}
 */
function getRandomName() {
    const firstNames = ['Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Oliver', 'Isabella', 'Elijah', 'Sophia', 
        'Lucas', 'Mia', 'Mason', 'Charlotte', 'Logan', 'Amelia', 'Ethan', 'Harper', 'Aiden', 'Evelyn', 'Jackson'];
    const lastNames = ['Smith', 'Johnson', 'Williams', 'Jones', 'Brown', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 
        'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Perez', 'Taylor', 'Anderson', 'Wilson', 'Moore', 'Jackson', 'Martin'];
    
    const randomFirstName = firstNames[Math.floor(Math.random() * firstNames.length)];
    const randomLastName = lastNames[Math.floor(Math.random() * lastNames.length)];
    
    return randomFirstName + ' ' + randomLastName;
}


/**
 * Create PDF of Driver acknowledgement to add to email.
 * @param {*} record 
 * @returns 
 */
function createDriverAcknowledgementPDF(record) {
    // Create folder if not exists and then get folder
    let folder = DriveApp.getFoldersByName(driveFolderNameUE);
    if (!folder.hasNext()) {
      folder = DriveApp.createFolder(driveFolderNameUE);
    } else {
      folder = folder.next();
    }

    // Create template document to attach
    const titleName = `Driver Acknowledgement: Order ${record.ID}`;
    const document = DocumentApp.create(titleName);

    // Move the document to the folder
    const fileId = document.getId();
    const file = DriveApp.getFileById(fileId);
    folder.addFile(file);
    DriveApp.getRootFolder().removeFile(file);
  
    // Add title to the document
    const header = document.addHeader();
    const title = header.insertParagraph(0, titleName);
    title.setAttributes({
      "FONT_SIZE": 20,
      "BOLD": true,
      "ITALIC": false,
      "UNDERLINE": true
    });
  
    // Add text to the body of the doc
    const body = document.getBody();
    // Add text to the document
    const templateMessage = `Please sign below to confirm that you have received all items from our restaurant, ` + 
    `${record.Restaurant}, as a third-party driver for ${record.Provider}, and that our staff has gone over ` +
    `all items in the order for order ${record.ID}, which was placed on ${record.Date}.`
    body.appendParagraph(templateMessage);
  
    // Add a space
    body.appendParagraph('');
  
    const font = getRandomSignatureFont();
    // Add the signature for a random name
    const signature = body.appendParagraph(getRandomName());
    signature.setAttributes({
      "FONT_SIZE": 16,
      "BOLD": true,
      "UNDERLINE": true,
      "ITALIC": true,
      "FONT_FAMILY": font
    });

    // Add a space
    body.appendParagraph('');

    // Add the date
    const signatureDate = body.appendParagraph('Date: ' + record.Date.toISOString().slice(0, 10));
    signatureDate.setAttributes({
      "FONT_SIZE": 14,
      "UNDERLINE": true,
      "BOLD": false,
    });
  
    // Save the document
    document.saveAndClose();
  
    // Convert the document to PDF
    const blob = document.getAs(MimeType.PDF);
  
    // Save the PDF file
    const pdfFile = folder.createFile(blob).setName(titleName + '.pdf');
  
    return pdfFile;
}

/**
 * For each of the dispute records made, send out an email to support to contest the issue.
 * @param {*[]} disputes 
 * @param {string} email
 */
function createEmail(disputes, email) {
    if (!disputes || disputes.length === 0) {
        Logger.info('No dispute records exist')
        throw new Error('No dispute records exist')
    }
    for (var i = 0; i < disputes.length; i++) {
        const record = disputes[i];
        const subject = `Adjustment Contest Order ${record.ID}`
        const body = `
          Dear ${record.Provider} Customer Service,
          
          I am writing on behalf of my restaurant, ${record.Restaurant}, 
          located at ${record.Address}, to address the ${record.Type} to order ${record.ID} on 
          ${record.Date} that have been charged to our account.
          We need to contest these charges and inform you that we have done our due diligence in 
          ensuring that all orders are fulfilled to the best of our ability. We assure you the reason of 
          ${record.Reason} is false.
          
          See the attached driver signature for confirmation.
          
          We take pride in providing high-quality food and excellent customer service to our valued 
          customers, which is why we take every order seriously. We make sure to read all instructions 
          carefully, verify all details with the customer over the phone, and get signature sign-off 
          from the driver to confirm that all items have been delivered.
          
          Despite our efforts, we have been charged adjustment fees for these orders in the amount of 
          ${record.Adjustment}. We believe that these charges are unwarranted, as we have done everything 
          in our power to fulfill the orders to the best of our ability. We cannot accept this.
          
          We kindly request that you urgently review and pay us back the adjustment fees.
          We value our partnership with ${record.Provider} and hope to continue to provide our customers 
          with high-quality food and exceptional service.
          
          Thank you for your attention to this matter. Especially in these trying times.
          
          Sincerely,
          
          Ace Haidrey
          ${record.Restaurant}
        `;
        
        // CC future foods on contests for virtual brands as then they need to ensure they pay us out adjustments too
        let cc = null;
        if (!nonFutureFoodsRestaurants.includes(record.Restaurant)) {
            cc = futureFoodsEmail;
        }
        // create the acknowledgement PDF to attach to email
        const pdfFile = createDriverAcknowledgementPDF(record);

        GmailApp.sendEmail(email, subject, body, {cc: cc, attachments: [pdfFile.getAs(MimeType.PDF)]});
    }
}

/**
 * Main entry point to contest UberEats orders based off of the email record they send weekly.
 * Schedule this to be on Mondays after the Sunday report sends the emails.
 */
function processUberOrderContests() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForContestUber * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(uberContestLabel);
  const threads = label.getThreads();
  let seenAnyError = false;

  deleteOldFilesInDrive();
  for (var i = 0; i < threads.length; i++) {
    // get all messages in the last N days
    if (threads[i].getLastMessageDate() > daysAgo) {
      const messages = threads[i].getMessages();
      // only get the first message to use - getMessages returns chronologically 
      if (messages.length > 0) {
        const firstMessage = messages[0].getPlainBody();
        const recordSummary = createEmailContext(firstMessage);
        Logger.log(recordSummary);
        seenAnyError = seenAnyError || recordSummary.error;
        createEmail(recordSummary.records, uberSenderEmail);
        Logger.log('Completed email sends for: ' + recordSummary);
      }
    }
  }
  if (seenAnyError) {
    throw new Error('Saw failed parsing. Check execution logs.');
  }
}