const defaultDaysAgoCutoff = 7;
const orderLabel = 'Orders';
const billingLabel = 'Billings';
const statsMap = {};

const Platform = {
  SLICE: 'Slice',
  MENUSTAR: 'Menustar',
  DOORDASH: 'Doordash',
  MENUFY: 'Menufy',
  EATSTREET: "Eatstreet",
  GRUBHUB: "Grubhub",
  TOAST: "Toast",
  BRYGID: "Brygid",
  SPEEDLINE: "Speedline",
  OFFICE_EXPRESS: "OfficeExpress",
  BEYONDMENU: "BeyondMenu",
  UBEREATS: 'UberEats',
  CHOWNOW: 'ChowNow'
};

/**
 * Function to clean up old order emails to archive and mark as read to reduce email box clutter.
 * This function is predecated that order labels are properly assigned.
 * The easier implementation will be to go through all Orders/* labels but App Script timeout
 * occurs in this instance. Therefore require manually invoking on each partner and have one catch all
 * function for the partners that are not manually added here.
 * NOTE, this gets the last 500 threads only. Larger sizes can use while loop with label.getThreads(start, maxThreads).
 */
function archiveOldOrderEmails(userLabel, daysAgoCutoff = defaultDaysAgoCutoff) {
  const startTime = Date.now();
  const daysAgo = new Date(Date.now() - daysAgoCutoff * 24 * 60 * 60 * 1000);
  const label = GmailApp.getUserLabelByName(userLabel);
  // if label not found in our gmail box error out
  if (!label) {
    throw new Error(`ERROR no label found for ${label}`)
  }
  const labelName = label.getName();
  statsMap[labelName] = 0;
  const threads = label.getThreads();
  Logger.log(`${labelName}, ${threads.length} emails threads checking to archive.`);
  for (var j = 0; j < threads.length; j++) {
        const currThread = threads[j];
        // if message is in inbox means not archived - mark read and archive it
        if (currThread.isInInbox() && currThread.getLastMessageDate() > daysAgo) {
          currThread.markRead();
          currThread.moveToArchive();
          statsMap[labelName] += 1;
        }
  }
  const elapsedTime = (Date.now() - startTime) / 1000;
  Logger.log(`${labelName}, ${statsMap[labelName]} emails archived and marked as read.`);
  Logger.log(`Total elapsed time so far: ${elapsedTime} seconds.`);
}

// BeyondMenu
function archiveOldOrderEmailsBeyondMenu() {
  const userLabel = `${orderLabel}/${Platform.BEYONDMENU}`;
  archiveOldOrderEmails(userLabel);
}

// Brygid
function archiveOldOrderEmailsBrygid() {
  const userLabel = `${orderLabel}/${Platform.BRYGID}`;
  archiveOldOrderEmails(userLabel);
}

// ChowNow
function archiveOldOrderEmailsChowNow() {
  const userLabel = `${orderLabel}/${Platform.CHOWNOW}`;
  archiveOldOrderEmails(userLabel);
}

// Doordash
function archiveOldOrderEmailsDoordash() {
  const userLabel = `${orderLabel}/${Platform.DOORDASH}`;
  archiveOldOrderEmails(userLabel);
}

// Eatstreet
function archiveOldOrderEmailsEatstreet() {
  const userLabel = `${orderLabel}/${Platform.EATSTREET}`;
  archiveOldOrderEmails(userLabel);
}

// Grubhub
function archiveOldOrderEmailsGrubhub() {
  const userLabel = `${orderLabel}/${Platform.GRUBHUB}`;
  archiveOldOrderEmails(userLabel);
}

// Menufy
function archiveOldOrderEmailsMenufy() {
  const userLabel = `${orderLabel}/${Platform.MENUFY}`;
  archiveOldOrderEmails(userLabel);
}

// Menustar
function archiveOldOrderEmailsMenustar() {
  const userLabel = `${orderLabel}/${Platform.MENUSTAR}`;
  archiveOldOrderEmails(userLabel);
}

// OfficeExpress
function archiveOldOrderEmailsOfficeExpress() {
  const userLabel = `${orderLabel}/${Platform.OFFICE_EXPRESS}`;
  archiveOldOrderEmails(userLabel);
}

// Slice
function archiveOldOrderEmailsSlice() {
  const userLabel = `${orderLabel}/${Platform.SLICE}`;
  archiveOldOrderEmails(userLabel);
}

// Toast
function archiveOldOrderEmailsToast() {
  const userLabel = `${orderLabel}/${Platform.TOAST}`;
  archiveOldOrderEmails(userLabel);
}

// All Others
function archiveOldOrderEmailsOthers() {
  const platforms = Object.values(Platform);
  const labels = GmailApp.getUserLabels();
  for (var i = 0; i < labels.length; i++) {
    const labelName = labels[i].getName();
    if ((labelName.indexOf(orderLabel + "/") > -1 || labelName === orderLabel) && !platforms.includes(labelName.replace(orderLabel + '/', ''))) {
      Logger.log(`${labelName} missing from the manual checks. Caught in the Others call.`)
      archiveOldOrderEmails(labelName);
    }
  }
}

// Grubhub Billing
function archiveOldBillingEmailsGrubhub() {
    const userLabel = `${billingLabel}/${Platform.GRUBHUB}`;
    archiveOldOrderEmails(userLabel, 30);
}

// Toast Billing
function archiveOldBillingEmailsToast() {
    const userLabel = `${billingLabel}/${Platform.TOAST}`;
    archiveOldOrderEmails(userLabel, 30);
}

// Doordash Billing
function archiveOldBillingEmailsDoordash() {
  const userLabel = `${billingLabel}/${Platform.DOORDASH}`;
  archiveOldOrderEmails(userLabel, 30);
}

// Speedline Billing
function archiveOldBillingEmailsSpeedline() {
  const userLabel = `${billingLabel}/${Platform.SPEEDLINE}`;
  archiveOldOrderEmails(userLabel, 30);
}

// Ordermark Billing
function archiveOldBillingEmailsOrdermark() {
  const userLabel = `${billingLabel}/Ordermark`;
  archiveOldOrderEmails(userLabel, 30);
}

// UberEats Billing
function archiveOldBillingEmailsUberEats() {
  const userLabel = `${billingLabel}/${Platform.UBEREATS}`;
  archiveOldOrderEmails(userLabel, 30);
}