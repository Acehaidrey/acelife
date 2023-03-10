const speedlineChargebackLabel = 'Billings/Speedline/Adjustments';
const followupLabel = 'Follow-Ups';

function addFollowupLabelToSpeedlineChargeback() {
    var label = GmailApp.getUserLabelByName(speedlineChargebackLabel);
    var threads = label.getThreads();
  
    var thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
  
    for (var i = 0; i < threads.length; i++) {
      var messages = threads[i].getMessages();
      for (var j = 0; j < messages.length; j++) {
        var message = messages[j];
        if (message.getDate() > thirtyDaysAgo) {
          message.addLabel(GmailApp.getUserLabelByName(followupLabel));
        }
      }
    }
  }
  