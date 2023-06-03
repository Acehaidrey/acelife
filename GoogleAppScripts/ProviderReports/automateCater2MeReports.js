const cater2meLabelName = 'Billings/Cater2Me'
const reportFolder = 'BusinessFinances'
const daysAgoCutoffForContestCater2Me = 15

/**
 * Uses the cater2me label setup in inbox to download the cater2me monthly reports. The provider names it
 * in a way to provide the month year in the attachment name, where we then label it, and move it to the correct
 * folder based off of the reporting month. All reports here exist for Aroma.
 * These reports are generally released on the 15th of each month.
 */
function saveCater2MeBillingAttachments() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForContestCater2Me * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(cater2meLabelName);
  const threads = label.getThreads().filter((thread) => thread.getLastMessageDate() > daysAgo);
  const parentFolder = DriveApp.getFoldersByName(reportFolder).next();
  const aromaBillingFolder = parentFolder.getFoldersByName('Aroma').next();
  for (var i = 0; i < threads.length; i++) {
    // get first message from original sender and get its attachment
    var message = threads[i].getMessages()[0];
    var attachments = message.getAttachments();
    
    for (var j = 0; j < attachments.length; j++) {
      var attachment = attachments[j];
      var fileName = attachment.getName();
      if (attachment.getContentType() === 'application/pdf') {
        var regex = /\b([A-Za-z]+)-(\d{4})\.pdf$/;
        var match = fileName.match(regex);
        if (match) {
          var month = match[1].toLowerCase();
          var year = match[2];
          var monthNumber = new Date(month + " 1, " + year).getMonth() + 1;
          var monthString = ("0" + monthNumber).slice(-2);
          var newName = 'cater2me_aroma_' + monthString + year + '.pdf'
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
          Logger.log('Adding file: ' + file);
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