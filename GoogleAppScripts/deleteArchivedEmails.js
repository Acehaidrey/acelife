// archive means no inbox
const archiveLabel = '-label:inbox';
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
  // Get all archived threads
  const threads = GmailApp.search(`${archiveLabel} before:${cutoffBeforeDate}`);
 
  for (var i = 0; i < threads.length; i++) {
    const messages = threads[i].getMessages();
    var hasMyEmail = false;
    var hasMyName = false;
    
    for (var j = 0; j < messages.length; j++) {
      if (messages[j].getFrom().includes(myEmail)) {
        hasMyEmail = true;
      }
      if (messages[j].getBody().includes(myName)) {
        hasMyName = true;
      }
    }
    // if the thread is not sent from my email, nor is it include my last name (other family members)
    // and if it has no custom labels, then we will remove the mail.
    if (!hasMyEmail && !hasMyName && threads[i].getLabels().length === 0) {
      threads[i].moveToTrash();
      countMessagesDeleted += 1;
    //   Logger.log(`Subj: ${threads[i].getFirstMessageSubject()}\nlabels: ${threads[i].getLabels()}\nmessages len: ${messages.length}}`);
    }
  }
  Logger.log(`${countMessagesDeleted} messages found and deleted.`);
  if (countMessagesDeleted < 1) {
    throw new Error('No messages found to delete');
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