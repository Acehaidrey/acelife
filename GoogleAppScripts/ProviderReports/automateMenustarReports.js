const menustarLabelName = 'Billings/Menustar'
const daysAgoCutoffForMenustar = 15

/**
 * Uses the menustar label setup in inbox to download the label monthly reports. The provider names it
 * in a way to provide the month year in the attachment name, where we then label it, and move it to the correct
 * folder based off of the reporting month.
 * These reports are generally released on the 3rd of each month.
 */
function saveMenustarBillingAttachments() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForMenustar * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(menustarLabelName);
  const threads = label.getThreads().filter((thread) => thread.getLastMessageDate() > daysAgo);
  const parentFolder = DriveApp.getFoldersByName('BusinessFinances').next();

  for (var i = 0; i < threads.length; i++) {
    // get first message from original sender and get its attachment
    var message = threads[i].getMessages()[0];
    var attachments = message.getAttachments();

    for (var j = 0; j < attachments.length; j++) {
      var attachment = attachments[j];
      var fileName = attachment.getName();
      const storeName = fileName.includes('Ameci') ? 'Ameci' : 'Aroma';
      const billingFolder = parentFolder.getFoldersByName(storeName).next();
      Logger.log('Processing file: ' + fileName);

      // if xlsx convert to csv
      if (attachment.getContentType().includes('spreadsheet') || attachment.getContentType().includes('officedocument')) {
        var convertedFile = convertXlsxToCsv(attachment);
        var data = convertedFile.getBlob().getDataAsString();
        var {csvFileName, monthFolder} = createFileName(data, storeName, billingFolder);
        // Add the file to the destination folder
        var file = monthFolder.createFile(convertedFile.getBlob());
        file.setName(csvFileName);
        // Remove the file from the source folder
        DriveApp.getFileById(convertedFile.getId()).setTrashed(true);
        Logger.log('Adding file: ' + file);
      }

      if (attachment.getContentType().includes('text')) {
        var data = attachment.getDataAsString();
        var {csvFileName, monthFolder} = createFileName(data, storeName, billingFolder);
        var csvBlob = attachment.getAs(MimeType.CSV);
        var file = monthFolder.createFile(csvBlob);
        file.setName(csvFileName);
        Logger.log('Adding file: ' + file);
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
function getOrCreateFolderBrygid(parentFolder, folderName) {
  var folders = parentFolder.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  } else {
    return parentFolder.createFolder(folderName);
  }
}

/**
 * Search the attachment file for the max date within all the dates in the file.
 * Generally, it should only have the records of a single month and then also use
 * the document name for retriving the store name.
 */
function getMaxDateFromCSV(data) {
  var csv = Utilities.parseCsv(data);
  var maxDate = null; // Initialize maxDate as null
  var today = new Date(); // Get the current date

  for (var i = 0; i < csv.length; i++) {
    var row = csv[i];
    var date = new Date(row[0]);

    if (date < today && (maxDate === null || date > maxDate)) {
      maxDate = date;
    }
  }

  var month = Utilities.formatDate(maxDate, Session.getScriptTimeZone(), 'MM');
  var year = Utilities.formatDate(maxDate, Session.getScriptTimeZone(), 'yyyy');

  return {
    month: month,
    year: year
  };
}


function convertXlsxToCsv(attachment) {
  var xlsxBlob = attachment.getAs(MimeType.MICROSOFT_EXCEL);
  // Create temporary file
  var tempFile = DriveApp.createFile(xlsxBlob);

  // Copy the file and convert to Google Sheets format
  var copiedFile = Drive.Files.copy({}, tempFile.getId(), {
    convert: true
  });

  // Open temporary file as a spreadsheet
  var tempSpreadsheet = SpreadsheetApp.openById(copiedFile.id);
  var tempSheet = tempSpreadsheet.getActiveSheet();

  var csvData = tempSheet.getDataRange().getDisplayValues().map(function(row) {
    return row.map(function(cell) {
      // Escape commas and quote the cell value
      var escapedCell = cell.replace(/"/g, '""');
      if (cell.indexOf(',') !== -1 || cell.indexOf('"') !== -1 || cell.indexOf('\n') !== -1) {
        escapedCell = '"' + escapedCell + '"';
      }
      return escapedCell;
    }).join(',');
  }).join('\n');

  // Delete temporary files
  DriveApp.getFileById(tempFile.getId()).setTrashed(true);
  DriveApp.getFileById(copiedFile.id).setTrashed(true);

  // Create the CSV file
  var csvBlob = Utilities.newBlob(csvData, MimeType.CSV, `${tempFile.getName().split('.')[0]}-converted.csv`);
  var csvFile = DriveApp.createFile(csvBlob);

  Logger.log(`Converted xlsx file ${tempFile.getName()} to csv: ${csvFile.getName()}`);
  return csvFile;
}

function createFileName(data, storeName, billingFolder) {
  var {month, year} = getMaxDateFromCSV(data);
  var newName = `menustar_${storeName.toLowerCase()}_${month}${year}.csv`;
  var yearFolder = getOrCreateFolderBrygid(billingFolder, year);
  var monthFolder = getOrCreateFolderBrygid(yearFolder, month);
  // if file exists to delete the older one then write new one
  var files = monthFolder.getFilesByName(newName);
  if (files.hasNext()) {
    var existingFile = files.next();
    existingFile.setTrashed(true); // delete existing file if exists
  }
  return {
    'csvFileName': newName,
    'monthFolder': monthFolder
  }
}
