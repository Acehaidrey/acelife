const restDepotSheetID = "11uwHNIlPYl8XVl-qI8BReoswPRN14NlCSL5BJ6htdng";

function sendEmailWithRestaurantDepotFormResponses() {
  var formSheet = SpreadsheetApp.openById(restDepotSheetID).getSheetByName('Form Responses 1');
  var lastRow = formSheet.getLastRow();
  var headerRow = formSheet.getRange(1, 1, 1, formSheet.getLastColumn()).getValues()[0];
  var today = new Date();
  var sevenDaysAgo = new Date(today.getTime() - (7 * 24 * 60 * 60 * 1000));
  var fifteenMinutesAgo = new Date(today.getTime() - (0.25 * 60 * 60 * 1000));

  for (var i = 2; i <= lastRow; i++) { //start at row 2 to exclude the header row
    var timestamp = new Date(formSheet.getRange(i, 1).getValue());
    if (timestamp > sevenDaysAgo) {  // change to fifteenMinutesAgo for scheduled
      var emailBody = ''; //reset emailBody for each row
      var restaurant = ''; //reset restaurant for each row
      var dateOfOrder = ''; //reset dateOfOrder for each row
      for (var j = 2; j <= formSheet.getLastColumn(); j++) { //start at column 2 to exclude the timestamp column
        var header = headerRow[j - 1];
        if (header) {
          header = header.replace(/\[(.*?)\]/g, '').trim();
        }
        var value = formSheet.getRange(i, j).getValue();
        if (value != '' && value != 0) {
          if (header === 'Date of Order') {
            dateOfOrder = new Date(value).toLocaleDateString();
          } else if (header === 'Restaurant') {
            restaurant = value;
          } else {
            if (header === 'Additional Items') {
              value = value.split('\n').join('\n');
              emailBody += value + '\n';
            } else {
              emailBody += header + ': ' + value + '\n';
            }
          }
        }
      }
      console.log(emailBody)
      if (emailBody != '') {
        MailApp.sendEmail({
          to: 'acehaidrey@gmail.com', // 'orders@aromapizzaandpasta.com',
          subject: '[Restaurant Depot Order] ' + restaurant + ' ' + dateOfOrder,
          body: emailBody
        });
      }
    }
  }
}
