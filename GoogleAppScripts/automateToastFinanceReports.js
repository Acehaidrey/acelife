// archive means no inbox
const archiveLabel = '-label:inbox';
// needs review label
const needsReviewLabel = '-label:promo-needsreview';
// arbitrary safeguard to only cleanup messages prior 2019 to begin
const cutoffBeforeDate = '2019/1/1';
const getDaysBeforeCutoff = 365 * 2; // 2 years ago
// condition check
const myEmail = 'acehaidrey@gmail.com';
const myName = 'haidrey';

/**
 * Delete archived emails who meet certain criteria.
 * Criteria in this case includes any message that is archived, do not have custom labels, and do not have
 * any responses from my personal email - aka if it has multiple threads where one of the emails is mine.
 */
function deleteArchivedEmailsWithoutLabels() {
  var countMessagesDeleted = 0;
  var countReviewLabelAdded = 0;
  // Get all archived threads
  const threads = GmailApp.search(`${archiveLabel} ${needsReviewLabel} before:${cutoffBeforeDate}`);
 
  for (var i = 0; i < threads.length; i++) {
    const messages = threads[i].getMessages();
    let hasMyEmail = false;
    let hasMyName = false;
    
    for (var j = 0; j < messages.length; j++) {
      // if (!messages[j].getFrom().includes(myEmail) && ! messages[j].getBody().includes(myName) && threads[i].getLabels().length === 0) {
        // console.log('------')
        // console.log(messages.length)
        // console.log(messages[j].getFrom())
        // console.log(messages[j].getFrom().includes(myEmail))
        // console.log(messages[j].getPlainBody())
        // console.log(messages[j].getPlainBody().includes(myName))
        // console.log(threads[i].getLabels())
        // console.log(threads[i].getLabels().length)
      // }
      if (messages[j].getFrom().includes(myEmail)) {
        hasMyEmail = true;
      } else {
        // if it does not meet add label here of Promo/NeedsReview
        if (threads[i].getLabels().length === 0) {
          threads[i].addLabel(GmailApp.getUserLabelByName("Promo/NeedsReview"));
          countReviewLabelAdded += 1;
        }
      }
      // if (messages[j].getBody().includes(myName)) {
      //   hasMyName = true;
      //   console.log('hasMyName ' + hasMyName)
      // }
    }
    // console.log(!hasMyEmail && !hasMyName && threads[i].getLabels().length === 0)
    // if the thread is not sent from my email, nor is it include my last name (other family members)
    // and if it has no custom labels, then we will remove the mail.
    if (!hasMyEmail && !hasMyName && threads[i].getLabels().length === 0) {
      threads[i].moveToTrash();
      countMessagesDeleted += 1;
    //   Logger.log(`Subj: ${threads[i].getFirstMessageSubject()}\nlabels: ${threads[i].getLabels()}\nmessages len: ${messages.length}}`);
    }
  }
  Logger.log(`${countMessagesDeleted} messages found and deleted.`);
  Logger.log(`${countReviewLabelAdded} messages found needing review.`);
  if (countMessagesDeleted < 1 && countReviewLabelAdded < 1) {
    throw new Error('No messages found to delete or label for review');
  }
}

/**
 * Converts a date object to a string version of it in format YYYY/MM/DD.
 * @param date {Date}
 * @returns {string}
 */
function getBeforeDate(date) {
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const formattedDate = `${year}/${month}/${day}`;
    return formattedDate;
}
