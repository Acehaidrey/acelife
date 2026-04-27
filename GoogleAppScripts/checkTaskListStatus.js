const VA_EMAIL = 'acehaidrey@gmail.com';
const OWNER_EMAIL = 'acehaidrey@gmail.com';

/**
 * Monthly task list status report.
 *
 * What this script does:
 * - Opens the shared task tracker spreadsheet.
 * - Finds the latest month tab using names like MMM/YYYY or MMM/YY.
 * - Reads the latest tab and finds tasks that are overdue and not yet completed.
 * - Treats Daily tasks specially: Date Completed is interpreted as the latest date
 *   through which the recurring task has been completed, regardless of Status.
 * - Groups those overdue tasks by Owner.
 * - Includes an upcoming-tasks section for work due in the next 3 days.
 * - Reports rows that are missing key fields and should be cleaned up.
 * - Sends a single email status report with one table per person.
 *
 * A task is considered overdue when:
 * - Date Due is before today, and
 * - for non-Daily tasks: Date Completed is blank and Status is not Completed
 * - for Daily tasks: Date Completed is blank or earlier than yesterday
 */

const TASK_LIST_CONFIG = {
  spreadsheetId: '1bnwEN-yY-ton6VLbAxyuu13LeAUzUAF9G_G6KCQ5Mro',
  recipients: `${VA_EMAIL}, ${OWNER_EMAIL}`,
  subjectPrefix: 'Daily'
};

/**
 * Sends the overdue-task status report for the latest month tab.
 */
function checkLatestTaskListStatus() {
  var spreadsheet = SpreadsheetApp.openById(TASK_LIST_CONFIG.spreadsheetId);
  var latestSheet = getLatestMonthSheet(spreadsheet);
  if (!latestSheet) {
    throw new Error('Could not find a month-formatted sheet tab like MMM/YYYY or MMM/YY.');
  }

  var reportData = getTaskStatusReportData(latestSheet);
  var recipients = getTaskStatusRecipients();
  var subject = `${TASK_LIST_CONFIG.subjectPrefix} - Task Status Report - ${latestSheet.getName()}`;
  var htmlBody = buildTaskStatusEmailHtml(
    latestSheet.getName(),
    getTaskSheetUrl(spreadsheet, latestSheet),
    reportData
  );

  MailApp.sendEmail({
    to: recipients,
    subject: subject,
    htmlBody: htmlBody
  });
}

/**
 * Builds a direct URL to a specific sheet tab.
 */
function getTaskSheetUrl(spreadsheet, sheet) {
  return `https://docs.google.com/spreadsheets/d/${spreadsheet.getId()}/edit#gid=${sheet.getSheetId()}`;
}

/**
 * Returns the recipient list for the report.
 * Falls back to the active user's email if no explicit recipients are configured.
 */
function getTaskStatusRecipients() {
  var configuredRecipients = String(TASK_LIST_CONFIG.recipients || '').trim();
  if (configuredRecipients) {
    return configuredRecipients;
  }
  return Session.getActiveUser().getEmail();
}

/**
 * Finds the latest month sheet using tab names like MMM/YYYY or MMM/YY.
 */
function getLatestMonthSheet(spreadsheet) {
  var best = null;

  spreadsheet.getSheets().forEach(function(sheet) {
    var parsed = parseMonthSheetName(sheet.getName());
    if (!parsed) return;

    if (!best || parsed.sortKey > best.sortKey) {
      best = {
        sheet: sheet,
        sortKey: parsed.sortKey
      };
    }
  });

  return best ? best.sheet : null;
}

/**
 * Parses month tab names like Apr/2026 or Apr/26.
 */
function parseMonthSheetName(sheetName) {
  var match = String(sheetName || '').trim().match(/^([A-Za-z]{3})\/(\d{2}|\d{4})$/);
  if (!match) {
    return null;
  }

  var monthMap = {
    jan: 1,
    feb: 2,
    mar: 3,
    apr: 4,
    may: 5,
    jun: 6,
    jul: 7,
    aug: 8,
    sep: 9,
    oct: 10,
    nov: 11,
    dec: 12
  };

  var month = monthMap[match[1].toLowerCase()];
  if (!month) {
    return null;
  }

  var yearText = match[2];
  var year = yearText.length === 2 ? 2000 + Number(yearText) : Number(yearText);
  if (!year) {
    return null;
  }

  return {
    month: month,
    year: year,
    sortKey: year * 100 + month
  };
}

/**
 * Reads the latest task sheet and returns grouped overdue tasks, upcoming tasks,
 * and incomplete rows.
 */
function getTaskStatusReportData(sheet) {
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) {
    return {
      tasksByPerson: {},
      incompleteRows: []
    };
  }

  var headers = values[0];
  var columnIndexes = {
    taskName: getHeaderIndex(headers, 'Task Name'),
    frequency: getHeaderIndex(headers, 'Frequency'),
    status: getHeaderIndex(headers, 'Status'),
    dateDue: getHeaderIndex(headers, 'Date Due'),
    dateCompleted: getHeaderIndex(headers, 'Date Completed'),
    personCharge: getHeaderIndex(headers, 'Owner'),
    notes: getHeaderIndex(headers, 'Notes')
  };

  Object.keys(columnIndexes).forEach(function(key) {
    if (columnIndexes[key] === -1) {
      throw new Error('Missing required column: ' + key);
    }
  });

  var today = getStartOfTodayForTasks();
  var yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  var tasksByPerson = {};
  var upcomingTasks = [];
  var incompleteRows = [];
  var skippedCount = 0;

  values.slice(1).forEach(function(row) {
    var status = String(row[columnIndexes.status] || '').trim();
    var taskName = String(row[columnIndexes.taskName] || '').trim();
    var frequency = String(row[columnIndexes.frequency] || '').trim();
    var personCharge = String(row[columnIndexes.personCharge] || '').trim() || 'Unassigned';
    var rawPersonCharge = String(row[columnIndexes.personCharge] || '').trim();
    var notes = columnIndexes.notes === -1 ? '' : String(row[columnIndexes.notes] || '').trim();
    var dateDue = parseSheetDate(row[columnIndexes.dateDue]);
    var dateCompleted = parseSheetDate(row[columnIndexes.dateCompleted]);
    var missingFields = [];

    if (status.toLowerCase() === 'skipped') {
      skippedCount += 1;
    }

    if (!taskName) {
      return;
    }

    if (!frequency) missingFields.push('Frequency');
    if (!status) missingFields.push('Status');
    if (!rawPersonCharge) missingFields.push('Owner');
    if (!dateDue) missingFields.push('Date Due');

    if (missingFields.length !== 0) {
      incompleteRows.push({
        taskName: taskName || '(blank)',
        frequency: frequency || '(blank)',
        status: status || '(blank)',
      dateDue: dateDue ? formatTaskDate(dateDue) : '(blank)',
      personCharge: rawPersonCharge || '(blank)',
      missingFields: missingFields.join(', ')
      });
    }

    if (!taskName || !dateDue) {
      return;
    }

    var upcomingCutoff = new Date(today);
    upcomingCutoff.setDate(upcomingCutoff.getDate() + 3);

    if (
      dateDue >= today &&
      dateDue <= upcomingCutoff &&
      status.toLowerCase() !== 'skipped' &&
      status.toLowerCase() !== 'completed'
    ) {
      upcomingTasks.push({
        taskName: taskName,
        frequency: frequency,
        status: status || '(blank)',
        dateDue: formatTaskDate(dateDue),
        dateDueSortKey: dateDue.getTime(),
        personCharge: personCharge,
        notes: notes
      });
    }

    if (dateDue >= today) {
      return;
    }

    if (status.toLowerCase() === 'skipped') {
      return;
    }

    var isDailyTask = frequency.toLowerCase() === 'daily';
    if (isDailyTask) {
      if (dateCompleted && dateCompleted >= yesterday) {
        return;
      }
    } else {
      if (dateCompleted) {
        return;
      }

      if (status.toLowerCase() === 'completed') {
        return;
      }
    }

    tasksByPerson[personCharge] = tasksByPerson[personCharge] || [];
    var daysOverdue = Math.floor((today.getTime() - dateDue.getTime()) / 86400000);
    tasksByPerson[personCharge].push({
      taskName: taskName,
      frequency: frequency,
      status: status,
      dateDue: formatTaskDate(dateDue),
      dateDueSortKey: dateDue.getTime(),
      daysOverdue: daysOverdue,
      personCharge: personCharge,
      notes: notes
    });
  });

  Object.keys(tasksByPerson).forEach(function(person) {
    tasksByPerson[person] = collapseWeeklyTasks(tasksByPerson[person]);
    tasksByPerson[person].sort(function(a, b) {
      if (a.isAbandoned && !b.isAbandoned) return -1;
      if (!a.isAbandoned && b.isAbandoned) return 1;
      if (a.maxDaysOverdue > b.maxDaysOverdue) return -1;
      if (a.maxDaysOverdue < b.maxDaysOverdue) return 1;
      if (a.dateDueSortKey < b.dateDueSortKey) return -1;
      if (a.dateDueSortKey > b.dateDueSortKey) return 1;
      return a.taskName.localeCompare(b.taskName);
    });
  });

  incompleteRows.sort(function(a, b) {
    return a.taskName.localeCompare(b.taskName);
  });

  upcomingTasks.sort(function(a, b) {
    if (a.dateDueSortKey < b.dateDueSortKey) return -1;
    if (a.dateDueSortKey > b.dateDueSortKey) return 1;
    return a.taskName.localeCompare(b.taskName);
  });

  return {
    tasksByPerson: tasksByPerson,
    upcomingTasks: upcomingTasks,
    incompleteRows: incompleteRows,
    skippedCount: skippedCount
  };
}

/**
 * Collapses duplicate overdue weekly tasks by owner/task/frequency and stacks
 * unique statuses, due dates, and notes as multi-line values.
 */
function collapseWeeklyTasks(tasks) {
  var collapsed = [];
  var weeklyGroups = {};

  tasks.forEach(function(task) {
    var isWeekly = String(task.frequency || '').trim().toLowerCase() === 'weekly';
    if (!isWeekly) {
      task.statusDisplay = task.status;
      task.dateDueDisplay = task.dateDue;
      task.notesDisplay = task.notes || '';
      task.maxDaysOverdue = task.daysOverdue;
      task.isAbandoned = String(task.status || '').trim().toLowerCase() === 'abandoned';
      collapsed.push(task);
      return;
    }

    var key = [
      task.personCharge,
      task.taskName,
      task.frequency
    ].join('||');

    if (!weeklyGroups[key]) {
      weeklyGroups[key] = {
        taskName: task.taskName,
        frequency: task.frequency,
        personCharge: task.personCharge,
        statusValues: [],
        dateDueValues: [],
        notesValues: [],
        dateDueSortKey: task.dateDueSortKey,
        maxDaysOverdue: task.daysOverdue,
        isAbandoned: false
      };
    }

    var group = weeklyGroups[key];
    if (group.statusValues.indexOf(task.status) === -1) {
      group.statusValues.push(task.status);
    }
    if (group.dateDueValues.indexOf(task.dateDue) === -1) {
      group.dateDueValues.push(task.dateDue);
    }
    if (task.notes && group.notesValues.indexOf(task.notes) === -1) {
      group.notesValues.push(task.notes);
    }
    if (task.dateDueSortKey < group.dateDueSortKey) {
      group.dateDueSortKey = task.dateDueSortKey;
    }
    if (task.daysOverdue > group.maxDaysOverdue) {
      group.maxDaysOverdue = task.daysOverdue;
    }
    if (String(task.status || '').trim().toLowerCase() === 'abandoned') {
      group.isAbandoned = true;
    }
  });

  Object.keys(weeklyGroups).forEach(function(key) {
    var group = weeklyGroups[key];
    collapsed.push({
      taskName: group.taskName,
      frequency: group.frequency,
      personCharge: group.personCharge,
      status: group.statusValues.join('\n'),
      statusDisplay: group.statusValues.join('\n'),
      dateDue: group.dateDueValues.join('\n'),
      dateDueDisplay: group.dateDueValues.join('\n'),
      daysOverdue: group.maxDaysOverdue,
      maxDaysOverdue: group.maxDaysOverdue,
      dateDueSortKey: group.dateDueSortKey,
      notes: group.notesValues.join('\n'),
      notesDisplay: group.notesValues.join('\n'),
      isAbandoned: group.isAbandoned
    });
  });

  return collapsed;
}

/**
 * Returns a case-insensitive header index.
 */
function getHeaderIndex(headers, targetHeader) {
  var normalizedTarget = String(targetHeader || '').trim().toLowerCase();
  for (var i = 0; i < headers.length; i++) {
    if (String(headers[i] || '').trim().toLowerCase() === normalizedTarget) {
      return i;
    }
  }
  return -1;
}

/**
 * Parses Google Sheets date values from either Date objects or string values.
 */
function parseSheetDate(value) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  var raw = String(value || '').trim();
  if (!raw) {
    return null;
  }

  var parsed = new Date(raw);
  if (isNaN(parsed.getTime())) {
    return null;
  }

  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

/**
 * Returns the start of today in the script time zone.
 */
function getStartOfTodayForTasks() {
  var timeZone = Session.getScriptTimeZone();
  var todayKey = Utilities.formatDate(new Date(), timeZone, 'yyyy-MM-dd');
  return new Date(todayKey + 'T00:00:00');
}

/**
 * Formats a task date for email output.
 */
function formatTaskDate(date) {
  var timeZone = Session.getScriptTimeZone();
  return Utilities.formatDate(date, timeZone, 'M/d/yyyy');
}

/**
 * Escapes HTML for email-safe output.
 */
function escapeTaskHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Escapes HTML and preserves line breaks for email table cells.
 */
function formatTaskCell(value) {
  return escapeTaskHtml(value).replace(/\n/g, '<br>');
}

/**
 * Builds the grouped HTML email body.
 */
function buildTaskStatusEmailHtml(sheetName, sheetUrl, reportData) {
  var tasksByPerson = reportData.tasksByPerson;
  var upcomingTasks = reportData.upcomingTasks;
  var incompleteRows = reportData.incompleteRows;
  var skippedCount = reportData.skippedCount || 0;
  var people = Object.keys(tasksByPerson).sort();
  var html = `<h2>Task Status Report</h2>`;
  html += `<p>Latest sheet checked: ${escapeTaskHtml(sheetName)}</p>`;

  html += '<div style="background: #fff3cd; border: 1px solid #f0d98a; padding: 12px 14px; margin: 12px 0 18px 0; border-radius: 6px;">';
  html += '<strong>Expectations</strong>';
  html += '<p style="margin: 8px 0 0 0;">Please do not fall behind on these dates. Be proactive. Even if I have not given instructions yet, first try the task yourself. Search Google, check the platform, and get as far as you can without help. If you get blocked, message me on Facebook right away and include what you already tried.</p>';
  html += '</div>';

  if (people.length === 0 && upcomingTasks.length === 0 && incompleteRows.length === 0) {
    html += '<p>No overdue, upcoming, or incomplete tasks were found on the latest sheet.</p>';
    return html;
  }

  if (people.length !== 0) {
    html += '<h3>Overdue Tasks</h3>';
    html += '<p>The following tasks are overdue and need immediate attention. Please reply right away with a status update on each late task so we can reassess what the issue is and whether any dates need to be adjusted.</p>';
  }

  people.forEach(function(person) {
    html += `<h3>${escapeTaskHtml(person)}</h3>`;
    html += '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">';
    html += '<tr><th>Task Name</th><th>Frequency</th><th>Status</th><th>Date Due</th><th>Days Overdue</th><th>Owner</th><th>Notes</th></tr>';

    tasksByPerson[person].forEach(function(task) {
      html += '<tr>';
      html += `<td>${formatTaskCell(task.taskName)}</td>`;
      html += `<td>${formatTaskCell(task.frequency)}</td>`;
      html += `<td>${formatTaskCell(task.statusDisplay || task.status)}</td>`;
      html += `<td>${formatTaskCell(task.dateDueDisplay || task.dateDue)}</td>`;
      html += `<td style="color: #c62828; font-weight: 700;">${escapeTaskHtml(task.daysOverdue)}</td>`;
      html += `<td>${formatTaskCell(task.personCharge)}</td>`;
      html += `<td>${formatTaskCell(task.notesDisplay || task.notes || '')}</td>`;
      html += '</tr>';
    });

    html += '</table>';
  });

  if (upcomingTasks.length !== 0) {
    html += '<h3>Upcoming In Next 3 Days</h3>';
    html += '<p>The following tasks are due soon and should be planned ahead of time.</p>';
    html += '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">';
    html += '<tr><th>Task Name</th><th>Frequency</th><th>Status</th><th>Date Due</th><th>Owner</th><th>Notes</th></tr>';

    upcomingTasks.forEach(function(task) {
      html += '<tr>';
      html += `<td>${escapeTaskHtml(task.taskName)}</td>`;
      html += `<td>${escapeTaskHtml(task.frequency)}</td>`;
      html += `<td>${escapeTaskHtml(task.status)}</td>`;
      html += `<td>${escapeTaskHtml(task.dateDue)}</td>`;
      html += `<td>${escapeTaskHtml(task.personCharge)}</td>`;
      html += `<td>${escapeTaskHtml(task.notes || '')}</td>`;
      html += '</tr>';
    });

    html += '</table>';
  }

  if (incompleteRows.length !== 0) {
    html += '<h3>Incomplete Rows</h3>';
    html += '<p>The following rows appear to be missing required task fields and should be cleaned up.</p>';
    html += '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">';
    html += '<tr><th>Task Name</th><th>Frequency</th><th>Status</th><th>Date Due</th><th>Owner</th><th>Missing Fields</th></tr>';

    incompleteRows.forEach(function(row) {
      html += '<tr>';
      html += `<td>${escapeTaskHtml(row.taskName)}</td>`;
      html += `<td>${escapeTaskHtml(row.frequency)}</td>`;
      html += `<td>${escapeTaskHtml(row.status)}</td>`;
      html += `<td>${escapeTaskHtml(row.dateDue)}</td>`;
      html += `<td>${escapeTaskHtml(row.personCharge)}</td>`;
      html += `<td>${escapeTaskHtml(row.missingFields)}</td>`;
      html += '</tr>';
    });

    html += '</table>';
  }

  if (skippedCount !== 0) {
    html += '<h3>Skipped Tasks</h3>';
    html += '<p style="margin-top: 16px;">';
    html += `<a href="${escapeTaskHtml(sheetUrl)}">Check the doc</a> `;
    html += `for skipped tasks. ${escapeTaskHtml(skippedCount)} task${skippedCount === 1 ? '' : 's'} skipped this month.`;
    html += '</p>';
  }

  return html;
}
