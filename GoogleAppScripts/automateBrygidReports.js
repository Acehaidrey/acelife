const brygidLabelName = 'Billings/Brygid'
const daysAgoCutoffForBrygid = 15

/**
 * Uses the brygid label setup in inbox to download the label monthly reports. The provider sents it out
 * mid-month where we then assume its for the prior month (aka 1/15/23 -> 12/2022), and move it to the correct
 * folder based off of the reporting month.
 * These reports are generally released on the 15th of each month.
 */
function saveBrygidBillingAttachments() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForBrygid * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(brygidLabelName);
  const threads = label.getThreads().filter((thread) => thread.getLastMessageDate() > daysAgo);
  const parentFolder = DriveApp.getFoldersByName('BusinessFinances').next();

  for (var i = 0; i < threads.length; i++) {
    // get first message from original sender and get its attachment
    var message = threads[i].getMessages()[0];
    var attachments = message.getAttachments();

    for (var j = 0; j < attachments.length; j++) {
      var attachment = attachments[j];

      var fileName = attachment.getName();
      const billingFolder = parentFolder.getFoldersByName('Ameci').next();
      if (attachment.getContentType().includes('html')) {
         var htmlContent = attachment.getDataAsString();

        // Extract the values using regular expressions
        var billingDateMatch = htmlContent.match(/<td[^>]*><b>Billing Date:<\/b><\/td>\s+<td[^>]*>(.*?)<\/td>/);
        var totalOrderCountMatch = htmlContent.match(/<td[^>]*><b>Total Order Count:<\/b><\/td>\s+<td[^>]*>(.*?)<\/td>/);
        var totalSalesMatch = htmlContent.match(/<td[^>]*><b>Total Sales:<\/b><\/td>\s+<td[^>]*>(.*?)<\/td>/);
        var averageCheckMatch = htmlContent.match(/<td[^>]*><b>Average Check:<\/b><\/td>\s+<td[^>]*>([\s\S]*?)<\/td>/);
        var totalServiceFeesMatch = htmlContent.match(/<td[^>]*><b>Total Service Fees:<\/b><\/td>\s+<td[^>]*>(.*?)<\/td>/);

        // Extract the values from the regex matches
        var billingDate = billingDateMatch ? billingDateMatch[1].trim() : "";
        var totalOrderCount = totalOrderCountMatch ? parseFloat(totalOrderCountMatch[1].replace(/[$,]/g, "")) : 0;
        var totalSales = totalSalesMatch ? parseFloat(totalSalesMatch[1].replace(/[$,]/g, "")) : 0;
        var averageCheck = averageCheckMatch ? parseFloat(averageCheckMatch[1].replace(/[$,]/g, "")) : 0;
        var totalServiceFees = totalServiceFeesMatch ? parseFloat(totalServiceFeesMatch[1].replace(/[$,]/g, "")) : 0;

        // Log the extracted values
        Logger.log("Billing Date: " + billingDate);
        Logger.log("Total Order Count: " + totalOrderCount);
        Logger.log("Total Sales: " + totalSales);
        Logger.log("Average Check: " + averageCheck);
        Logger.log("Total Service Fees: " + totalServiceFees);

        // Prepare the CSV data
        var csvData = [
          ["Platform", "Billing Date", "Total Order Count", "Total Sales", "Average Check", "Total Service Fees"],
          ["Brygid", billingDate, totalOrderCount, totalSales, averageCheck, totalServiceFees]
        ];
        // Convert the CSV data to a string
        var csvString = csvData.map(row => row.join(",")).join("\n");

        // Get the month and year of the previous month to record for billing
        var currentDate = new Date(billingDate);
        currentDate.setMonth(currentDate.getMonth() - 1);
        var month = (currentDate.getMonth() + 1).toString().padStart(2, '0'); // Adding 1 since getMonth() returns zero-based month (0-11), zero pad
        var year = currentDate.getFullYear();

        // Create a file in Google Drive
        var fileName = `brygid_ameci_billing_summary_${month}${year}.csv`;
        var yearFolder = getOrCreateFolderBrygid(billingFolder, year);
        var monthFolder = getOrCreateFolderBrygid(yearFolder, month);
        // if file exists to delete the older one then write new one
        var files = monthFolder.getFilesByName(fileName);
        if (files.hasNext()) {
          var existingFile = files.next();
          existingFile.setTrashed(true); // delete existing file
        }
        var file = monthFolder.createFile(fileName, csvString, MimeType.CSV);
        file.setName(fileName);
        Logger.log("CSV file created: " + file + ' ' + file.getUrl());
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
