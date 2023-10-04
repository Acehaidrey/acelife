const bmInfoEmail = 'info@beyondmenu.com';

function automateBeyondMenuFinancesEmail(monthReport=null) {
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
  const body = `Hi team,<br><br>My name is Ace Haidrey. I am the owner and 
    operator of the store Ameci Pizza and Pasta in Lake Forest at 25431 Trabuco Road 
    (Store ID 38958), and Aroma Pizza and Pasta in Lake Forest at 20491 Alton Parkway 
    (Store ID 52204). I need your help. I need to get my finance report for the month of 
    ${monthReport} for all of my stores Aroma and Ameci. Can you put it in one transactions 
    CSV please and include all information? If there is no transactions, can you just return me 
    to have all zeros so I can see if there were any account charges.
    <br><br>Thank you very much in advance.`;

  // Create the draft email
  const draft = GmailApp.createDraft(
    [bmInfoEmail].join(','),
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
