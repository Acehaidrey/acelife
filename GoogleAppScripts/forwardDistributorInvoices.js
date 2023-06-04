AMECI_FWD_EMAIL = '9320.Amec@xcinvoice.com'
AROMA_FWD_EMAIL = '7907.Arom@xcinvoice.com'
PERSONAL_EMAIL = 'acehaidrey@gmail.com'

function processEmailAttachments(labelName, days, attachmentFilter = null) {
  const label = GmailApp.getUserLabelByName(labelName);
  const daysAgo = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  const threads = label.getThreads().filter((thread) => thread.getLastMessageDate() > daysAgo);

  for (var i = 0; i < threads.length; i++) {
    var messages = threads[i].getMessages();
    for (var k = 0; k < 3; k++) {
      var message = messages[k];
      Logger.log(message);
      if (message && !isForwardedMessage(message)) {
        var attachments = message.getAttachments();
        for (var j = 0; j < attachments.length; j++) {
          var attachment = attachments[j];
          if (attachmentFilter && typeof attachmentFilter === 'function') {
            if (!attachmentFilter(attachment)) {
              continue; // Skip processing this attachment based on custom function result
            }
          }
          var fileName = attachment.getName();
          var textContent = saveAttachmentToDriveAndGetTextForVendor(attachment);
          if (textContent.toLowerCase().includes("ameci")) {
            message.forward(AMECI_FWD_EMAIL);
            Logger.log(`Forwarded attachment ${fileName} to ${AMECI_FWD_EMAIL} for xtraChef invoice processing`);
          }
          if (textContent.toLowerCase().includes("aroma")) {
            message.forward(AROMA_FWD_EMAIL);
            Logger.log(`Forwarded attachment ${fileName} to ${AROMA_FWD_EMAIL} for xtraChef invoice processing`);
          }
        }
      } else {
        if (message) {
          Logger.log(`Following message subject indicates it is a forwarded message: ${message.getSubject()}`);
        }
      }
    }
  }
}


/**
 * Checks to see if the message is forwarded by identifying the to, from, and subject.
 */
function isForwardedMessage(message) {

  if (!message) {
    return false;
  }

  const subj = message.getSubject();
  const frm = message.getFrom();
  const to = message.getTo();

  if (subj.toLowerCase().includes('fwd:') && frm.includes(PERSONAL_EMAIL)) {
    return true;
  }
  if (to.includes(AROMA_FWD_EMAIL) || to.includes(AMECI_FWD_EMAIL)) {
    return true;
  }
  return false;
}


function saveAttachmentToDriveAndGetTextForVendor(attachment) {
  // save the PDF from email to Drive
  var fileBlob = attachment.copyBlob();
  var fileName = attachment.getName();
  var file = DriveApp.createFile(fileBlob).setName(fileName);
  // use OCR to convert PDF -> Text file
  const { id } = Drive.Files.insert(
    {
      title: file.getName().replace(/\.pdf$/, ''),
      mimeType: file.getMimeType(),
    },
    fileBlob,
    {
      ocr: true,
      ocrLanguage: 'en',
      fields: 'id',
    }
  );
  const textContent = DocumentApp.openById(id).getBody().getText();
  DriveApp.getFileById(id).setTrashed(true);
  DriveApp.getFileById(file.getId()).setTrashed(true);
  return textContent;
}


function forwardMaisanosInvoices() {
  processEmailAttachments('Billings/Maisanos', 30)
}

function forwardConcordInvoices() {
  processEmailAttachments('Billings/Concord', 30)
}

function forwardVieleInvoices() {
  processEmailAttachments('Billings/Viele', 30)
}

function forwardSyscoInvoices() {
  processEmailAttachments('Billings/Sysco', 30)
}
