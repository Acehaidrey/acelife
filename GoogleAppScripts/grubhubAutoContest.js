const grubhubContestLabel = 'Billings/Grubhub/Adjustments';
const grubhubSenderEmail = 'restaurants@grubhub.com';
const driveFolderName = 'GrubhubAdjustments';
const daysAgoCutoffForContest = 1;

/**
 * Save the email attachment passed to Drive and convert the PDF to a Text file.
 * @param {*} attachment 
 * @returns {string} - PDF content as text
 */
function saveAttachmentToDriveAndGetText(attachment) {
  // Create folder if not exists and then get folder
  let folder = DriveApp.getFoldersByName(driveFolderName);
  if (!folder.hasNext()) {
    folder = DriveApp.createFolder(driveFolderName);
  } else {
    folder = folder.next();
  }
  // save the PDF from email to Drive
  folder = DriveApp.getFoldersByName(driveFolderName).next();
  var fileBlob = attachment.copyBlob();
  var fileName = attachment.getName();
  var file = folder.createFile(fileBlob).setName(fileName);
  // use OCR to convert PDF -> Text file
  const { id } = Drive.Files.insert(
    {
      title: file.getName().replace(/\.pdf$/, ''),
      mimeType: file.getMimeType(),
    },
    fileBlob,
    {
      ocr: true,
      ocrLanguage: 'en',
      fields: 'id',
    }
  );
  const textContent = DocumentApp.openById(id).getBody().getText();
  DriveApp.getFileById(id).setTrashed(true);
  return textContent;
}

/**
 * Parse the email PDF converted text file and get the relevant information for contesting information.
 * @param {string} pdfText 
 * @returns {*[]}
 */
function createEmailContextGH(pdfText) {
    const disputeRecords = [];
    const pdfTextList = pdfText.split('\n').map((value) => value.trim());
    const restaurant = pdfTextList[1];
    // specific to our case where always have zipcode as 92630 to get address
    const cityInfoIndex = pdfTextList.findIndex(item => item.includes('92630'));
    const address = pdfTextList[cityInfoIndex - 1];
    const cityInfo = pdfTextList[cityInfoIndex];
    // find where Order Detail is in the output then get all values after it
    let orderDetailText = pdfText.substring(pdfText.indexOf("Order Detail") + "Order Detail".length).trim();
    // remove the last line as it is the total day summary of order details
    orderDetailText = orderDetailText.replace(pdfTextList[pdfTextList.length - 1], '');
    // find Total in the result
    const totalIndex = orderDetailText.indexOf("Total");
    // const keys = orderDetailText.substring(0, totalIndex + "Total".length).split(' ');
    let recordsText = orderDetailText.substring(totalIndex + "Total".length, orderDetailText.length).trim();
    // split the line by white space for each record and split records by the orderId that is just a single line remove it
    recordsText = recordsText.split('\n')
    .filter(line => {
      const words = line.trim().split(' ');
      return !line.match(/[A-Z]-\d+/) || words.length > 1;
    });
    recordsText = recordsText.join(' ').replace(/\s+/g,' ');
    recordsText = recordsText.split(/([A-Z]-\d+)/).filter(Boolean);
    // reduce so we have combined record like below
    // O-783021753230271 Cancelation of 02/26/23 10:15 PM -$24.74 $.00 -$1.92 $.00 -$26.66
    // filter out Adjust and Cancel orders only
    const groupedRows = recordsText.reduce((acc, cur, i) => {
      if (i % 2 === 0) {
        acc.push([cur.trim(), recordsText[i+1].trim()]);
      }
      return acc;
    }, []).map(arr => arr.join(' ')).filter(row => row.includes('Adjust') || row.includes('Cancel'));
    for (var i = 0; i < groupedRows.length; i++) {
      const splitRow = groupedRows[i].replace(/\s+/g,' ').trim().split(' ');
      // parse the record to best of our ability for info we need
      const record = {
        ID: splitRow[0],
        Type: groupedRows[i].includes('Adjust') ? 'adjustment' : 'cancellation',
        Date: groupedRows[i].match((/\d{2}\/\d{2}\/\d{2}/))[0],
        Time: groupedRows[i].match(/\d{1,2}:\d{2}\s(AM|PM)/)[0],
        Subtotal: splitRow[splitRow.length - 5],
        Delivery: splitRow[splitRow.length - 4],
        Tax: splitRow[splitRow.length - 3],
        Tip: splitRow[splitRow.length - 2],
        Total: splitRow[splitRow.length - 1],
        Restaurant: restaurant,
        Address: address + ', ' + cityInfo,
        Provider: 'Grubhub'
      };
      disputeRecords.push(record);
    }
    return disputeRecords;
}

/**
 * For each of the dispute records made, send out an email to support to contest the issue.
 * @param {*[]} disputes 
 * @param {string} email
 */
function createEmailGH(disputes, email) {
    if (!disputes || disputes.length === 0) {
        Logger.info('No dispute records exist')
        throw new Error('No dispute records exist')
    }
    for (var i = 0; i < disputes.length; i++) {
        const record = disputes[i];
        const subject = `Adjustment Contest Order ${record.ID}`
        const body = `
        Dear ${record.Provider} Customer Service,

        I am writing on behalf of my restaurant, ${record.Restaurant}, located at ${record.Address}, 
        to address the ${record.Type} to order ${record.ID} on ${record.Date} that have been charged 
        to our account. We need to contest these charges and inform you that we have done our due 
        diligence in ensuring that all orders are fulfilled to the best of our ability.
        
        We take pride in providing high-quality food and excellent customer service to our valued 
        customers, which is why we take every order seriously. We make sure to read all instructions 
        carefully, verify all details with the customer over the phone, and get signature sign-off 
        from the driver to confirm that all items have been delivered.
        
        Despite our efforts, we have been charged adjustment fees for these orders in the amount of 
        ${record.Total}. We believe that these charges are unwarranted, as we have done everything 
        in our power to fulfill the orders to the best of our ability. We cannot accept this.
        
        We kindly request that you urgently review and pay us back the adjustment fees, as well as 
        any delivery fees that may apply, ${record.Delivery}. We value our partnership with ${record.Provider} 
        and hope to continue to provide our customers with high-quality food and exceptional service.
        
        Thank you for your attention to this matter. Especially in these times.
        
        Sincerely,
        
        Ace Haidrey
        ${record.Restaurant}`;        
        GmailApp.sendEmail(email, subject, body);
    }
}

/**
 * Delete files older than 30 days in the Drive location we copy PDFs to.
 */
function deleteOldFilesInDriveGH(deleteDaysAgo = 30) {
  // Set the ID of the folder you want to delete files from
  const driveFolder = DriveApp.getFoldersByName(driveFolderName).next();
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
 * Main entry point to contest Grubhub orders based off of the email record they send daily.
 */
function processGrubhubOrderContests() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForContest * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(grubhubContestLabel);
  const threads = label.getThreads();
  deleteOldFilesInDriveGH();
  for (var i = 0; i < threads.length; i++) {
    // get all messages in the last N days
    if (threads[i].getLastMessageDate() > daysAgo) {
      var messages = threads[i].getMessages();
      for (var j = 0; j < messages.length; j++) {
        const attachments = messages[j].getAttachments();
        // if no attachments
        if (!attachments || attachments.length === 0) {
          continue;
        }
        for (var k = 0; k < attachments.length; k++) {
          Logger.log(attachments[k].getName())
          // no library to read PDF directly - save to Drive and leverage there to read to text
          if (attachments[k].getContentType() === 'application/pdf') {
            const text = saveAttachmentToDriveAndGetText(attachments[k]);
            const disputeRecs = createEmailContextGH(text);
            Logger.log(text);
            Logger.log(disputeRecs);
            createEmailGH(disputeRecs, grubhubSenderEmail);
          }
        }
      }
    }
  }
}