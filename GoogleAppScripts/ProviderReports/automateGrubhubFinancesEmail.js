const accountManagerEmail = 'jgrier@grubhub.com';
const grubhubSupportEmail = 'restaurants@grubhub.com';

function automateGrubhubFinancesEmail(monthReport=null) {
  // Get the current month and year
  const today = new Date();
  const month = today.getMonth() + 1; // Months are zero-based
  const year = today.getFullYear();

  if (!monthReport) {
    // Set the desired monthReport value
    monthReport = `${month}/${year}`;
  }

  // Compose the email content
  const subject = `Finance Report Request - ${monthReport}`;
  const body = `Hi team,<br><br>
  My name is Ace Haidrey. I am the owner and operator of the store Ameci Pizza and Pasta in Lake Forest at 25431 Trabuco Road, 
  and Aroma Pizza and Pasta in Lake Forest at 20491 Alton Parkway, along with Trattoria Contadina and The Wing Shop that are at 
  the same address as they are virtual restaurants. 
  I need your help. I need to get my finance report for the month of ${monthReport} for all of my stores Aroma, Ameci, 
  Trattoria, and Wingshop. Can you put it in one transactions CSV please and include all information?<br><br>
  I know I can go into the dashboard to get it, but this way is easier for me as I have automation set up 
  to ingest the data from my email into my finance dashboard until your group allows 
  for us to leverage your APIs.<br><br>
  Thank you very much in advance.`;

  // Create the draft email
  const draft = GmailApp.createDraft(
    [accountManagerEmail, grubhubSupportEmail].join(','),
    subject,
    '',
    { htmlBody: body }
  );

  // Apply the "followup" label to the draft
  // const followupLabel = GmailApp.getUserLabelByName('Follow Ups');
  // draft.addLabel(followupLabel);

  // Send the draft email
  draft.send();
}
