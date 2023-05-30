const speedlineChargebackLabel = 'Billings/Speedline/Adjustments';
const toastChargebackLabel = 'Billings/Toast/Adjustments';
const followupLabel = 'Follow Ups';

function addGenericFollowUpLabel(labelName, daysAgoCutoff = 30) {
    var label = GmailApp.getUserLabelByName(labelName);
    var fulabel = GmailApp.getUserLabelByName(followupLabel);
    var threads = label.getThreads();

    var dt = new Date();
    dt.setDate(dt.getDate() - daysAgoCutoff);

    for (var i = 0; i < threads.length; i++) {
      var messages = threads[i].getMessages();
      for (var j = 0; j < messages.length; j++) {
        var message = messages[j];
        if (message.getDate() > dt) {
          fulabel.addToThread(threads[i]);
          Logger.log(`Add Follow Up label to ${threads[i].getFirstMessageSubject()}`);
        }
      }
    }
}

function addFollowupLabelToSpeedlineChargeback() {
  addGenericFollowUpLabel(speedlineChargebackLabel, 30)
}

function addFollowupLabelToToastChargeback() {
  addGenericFollowUpLabel(toastChargebackLabel, 30)
}