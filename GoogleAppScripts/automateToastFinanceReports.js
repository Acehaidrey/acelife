const toastFinanceLabelName = 'Billings/Toast/Processing'
const reportFolderBF = 'BusinessFinances'
const daysAgoToastFinance = 15

/**
 * Uses the toast finance label setup in inbox to download the toast monthly processing reports. The provider names it
 * in a way to provide the month year in the attachment name, where we then label it, and move it to the correct
 * folder based off of the reporting month. All reports here exist for Aroma.
 * These reports are generally released on the 5th of each month.
 */
function saveToastFinanceAttachments() {
  const daysAgo = new Date(Date.now() - daysAgoToastFinance * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(toastFinanceLabelName);
  const threads = label.getThreads().filter((thread) => thread.getLastMessageDate() > daysAgo);
  const parentFolder = DriveApp.getFoldersByName(reportFolderBF).next();
  const aromaBillingFolder = parentFolder.getFoldersByName('Aroma').next();
  for (var i = 0; i < threads.length; i++) {
    // get first message from original sender and get its attachment
    var message = threads[i].getMessages()[0];
    var attachments = message.getAttachments();
    
    for (var j = 0; j < attachments.length; j++) {
      var attachment = attachments[j];
      var fileName = attachment.getName();
      Logger.log('Processing file: ' + fileName);
      if (attachment.getContentType() === 'application/pdf') {
        var regex = /_([A-Za-z]+)_([0-9]{4})/;
        var match = fileName.match(regex);
        if (match) {
          var month = match[1].toLowerCase();
          var year = match[2];
          var monthNumber = new Date(month + " 1, " + year).getMonth() + 1;
          var monthString = ("0" + monthNumber).slice(-2);
          var newName = 'toast_aroma_processing_' + monthString + year + '.pdf'
          var yearFolder = getOrCreateFolder(aromaBillingFolder, year);
          var monthFolder = getOrCreateFolder(yearFolder, monthString);
          // if file exists to delete the older one then write new one
          var files = monthFolder.getFilesByName(newName);
          if (files.hasNext()) {
            var existingFile = files.next();
            existingFile.setTrashed(true); // delete existing file
          }
          var file = monthFolder.createFile(attachment);
          file.setName(newName);
          Logger.log('Adding file: ' + file + ' to location: ' + monthFolder);
        }
      }
    }
  }
}

/**
 * Check if a folder exists or create it if not.
 * @param {*} parentFolder Top level folder name looking into
 * @param {*} folderName Folder name looking for or creating
 * @returns DriveFolder
 */
function getOrCreateFolder(parentFolder, folderName) {
  var folders = parentFolder.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  } else {
    return parentFolder.createFolder(folderName);
  }
}
