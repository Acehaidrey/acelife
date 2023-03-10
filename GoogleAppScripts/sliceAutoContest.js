const sliceContestLabel = 'Billings/Slice/Adjustments';
const daysAgoCutoffForContestSlice = 1;
const forwardingRecipients = ["support@slicelife.com", "ann.t@slicelife.com"];


function processSliceOrderContests() {
  const daysAgo = new Date(Date.now() - daysAgoCutoffForContestSlice * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(sliceContestLabel);
  if (!label) {
    Logger.log(`Label "${sliceContestLabel}" not found.`);
    return;
  }
  // only get threads that are in the past X days
  const threads = label.getThreads().filter((row) => row.getLastMessageDate() > daysAgo);
  threads.forEach(thread => {
    const messages = thread.getMessages();
    if (messages) {
      const originalMessage = messages[0];
      const orderNumber = getOrderNumber(originalMessage.getSubject());
      const subject = "[CONTEST VOID ORDER] FWD: " + originalMessage.getSubject();
      const body = createEmailBody(orderNumber, originalMessage);
      const draft = GmailApp.createDraft(forwardingRecipients.join(","), subject, '', {htmlBody: body});
      draft.send();
      Logger.log(`Respond to email for order "${orderNumber}" | email id ${thread.getId()}.`);
    }
  });
}

/**
 * The subject is 'Void Notice for Slice Order 83102666'.
 * We want to extract the order id from the string.
 */
function getOrderNumber(subject) {
  const orderNumberRegex = /Void\sNotice\sfor\sSlice\sOrder\s(\w+)/i;
  const match = subject.match(orderNumberRegex);
  if (match && match.length >= 2) {
    return match[1];
  }
  return null;
}

/**
 * Creates an email body html content to format and send as part of contest.
 * @param {string} orderId 
 * @param {GmailMessage} message 
 * @returns {string} - html string
 */
function createEmailBody(orderId, message) {
    const responseBody = `
        Dear Slice service team,
        <br><br>
        I am writing to address the issue we have with in regards to order ${orderId} with this void notice. 
        As a restaurant, we have always taken our responsibility seriously in ensuring that all orders are prepared and 
        delivered to our customers in a timely manner.
        <br><br>
        We have made all the necessary preparations to ensure that our food is of the highest quality and meets the 
        expectations of our customers. Once the order has been prepared, we ensure that it is handed over to the 
        customer promptly or delivered within the time frame we committed to.
        <br><br>
        We do not allow refunds unless it has been verified by me personally, in writing here. It is Slice's 
        responsibility to ensure that we are paid out for the orders that we have accepted, prepared, and deployed. 
        We understand that it is Slice's responsibility to ensure that we are paid out, whether it comes from the 
        customer or if it comes from your commissions.
        <br><br>
        We appreciate your attention to this matter and hope that you can resolve this issue in a timely and 
        efficient manner. We take pride in the quality of our food and service, and we hope to continue our 
        partnership with Slice to provide the best possible experience to our customers.
        <br><br>
        Thank you for your understanding and cooperation.
    `;
    const html = '<p>' + responseBody.trim() + '</p><br><br>' + message.getBody();
    return html;
}