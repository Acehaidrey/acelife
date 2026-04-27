/**
 * Closing report validation and notification script.
 *
 * What this script does:
 * - Checks each restaurant's "Form Responses 1" sheet by Date of Operation.
 * - Verifies there is exactly one row per expected Date of Operation in the requested window.
 * - Flags missing dates and duplicate dates.
 * - Auto-corrects the "Day of Week" column so it matches Date of Operation.
 * - Treats a Notes value of "0" as blank, clears it in the sheet, and excludes it from emails.
 * - Includes rows with non-empty notes in a dedicated Notes section.
 * - Validates required provider total columns and flags rows where those totals are blank or zero.
 * - Lists rows where Other Total is non-zero so those inputs can be reviewed.
 * - Reports if expected provider total columns are missing from the sheet.
 * - Includes employee names for duplicate rows, provider-total issues, and note-bearing rows.
 * - Validates expected numeric sheet columns inside the checked date window only.
 * - Auto-fixes safe numeric formatting issues in the sheet and reports what changed,
 *   including removal of commas, dollar signs, periods used as formatting noise,
 *   parentheses negatives, and stray whitespace.
 * - Accepts numbers with up to 2 decimal places.
 * - Reports numeric values that could not be safely fixed and should be investigated.
 * - Can send either restaurant-specific emails or a combined Ameci + Aroma email separated by <hr>.
 *
 * Date windows currently supported:
 * - Daily: last 7 completed Date of Operation days.
 * - Monthly: previous full calendar month.
 */
const sheetInfo = {
  'Aroma': {
    sheetID: '11xO2gPNy3XK2_z04k8JexVsFw2hPkcg8jh4ea3ayjV4',
    formUrl: 'https://docs.google.com/forms/d/e/1FAIpQLSf4RoE3HpezRQb3o1mWElqZNOAtsfzWNvxqM_R6ZplSGIJcvA/viewform',
    emailID: 'orders@aromapizzaandpasta.com, acehaidrey@gmail.com',
    requiredProviderColumns: [
      { label: 'UberEats Total', header: 'UberEats Total' },
      { label: 'Slice Total', header: 'Slice Total' },
      { label: 'Doordash Total', header: 'Doordash Total' },
      { label: 'Grubhub Total', header: 'Grubhub Total' }
    ],
    nonIntegerHeaders: [
      'Timestamp',
      'Employee Name',
      'Date of Operation',
      'Day of Week',
      'Notes',
      'Other Total'
    ]
  },
  'Ameci': {
    sheetID: '1PzM1sPE9oBnEpsFDRvmt1CJCA-AQYAnZAhQBmcWJMag',
    formUrl: 'https://docs.google.com/forms/d/e/1FAIpQLSeiitYvdXpxfQovWLGT3dWardSriO6Aj2visjVSMwCPJ3C0bQ/viewform',
    emailID: 'orders@amecilakeforest.com, acehaidrey@gmail.com',
    requiredProviderColumns: [
      { label: 'UberEats Total', header: 'UberEats Total' },
      { label: 'Slice Total', header: 'Slice Total' },
      { label: 'Doordash Total', header: 'Doordash Total' },
      { label: 'Grubhub Total', header: 'Grubhub Total' }
    ],
    nonIntegerHeaders: [
      'Timestamp',
      'Employee Name',
      'Date of Operation',
      'Day of Week',
      'Notes',
      'Other Total'
    ]
  }
};

/**
 * Formats a Date as a stable yyyy-MM-dd key for comparisons and grouping.
 */
function formatDateKey(date, timeZone) {
  return Utilities.formatDate(date, timeZone, 'yyyy-MM-dd');
}

/**
 * Formats a Date for human-readable email output.
 */
function formatDisplayDate(date, timeZone) {
  return Utilities.formatDate(date, timeZone, 'M/d/yyyy');
}

/**
 * Returns a Date representing the start of today in the script time zone.
 * This is used so checks only consider completed operation dates.
 */
function getStartOfToday(timeZone) {
  var todayKey = Utilities.formatDate(new Date(), timeZone, 'yyyy-MM-dd');
  return new Date(todayKey + 'T00:00:00');
}

/**
 * Normalizes a header value for case-insensitive matching.
 */
function normalizeHeaderName(value) {
  return String(value || '').trim().toLowerCase();
}

/**
 * Finds a 1-based column index by exact header match.
 * Returns -1 if the header is not found.
 */
function getColumnIndexByHeader(headers, headerName) {
  var normalizedTarget = normalizeHeaderName(headerName);
  for (var i = 0; i < headers.length; i++) {
    if (normalizeHeaderName(headers[i]) === normalizedTarget) {
      return i + 1;
    }
  }
  return -1;
}

/**
 * Finds a 1-based column index by header prefix match.
 * Returns -1 if no matching header is found.
 */
function getColumnIndexByHeaderPrefix(headers, headerPrefix) {
  var normalizedPrefix = normalizeHeaderName(headerPrefix);
  for (var i = 0; i < headers.length; i++) {
    if (normalizeHeaderName(headers[i]).indexOf(normalizedPrefix) === 0) {
      return i + 1;
    }
  }
  return -1;
}

/**
 * Returns the expected full weekday name for a given Date.
 */
function getExpectedDayOfWeek(date, timeZone) {
  return Utilities.formatDate(date, timeZone, 'EEEE');
}

/**
 * Escapes values for safe inclusion in HTML email bodies.
 */
function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Parses a sheet cell into a numeric value.
 * Supports plain numbers, currency formatting, commas, whitespace, and (123) negatives.
 * Returns null when the cell is blank or non-numeric.
 */
function parseNumericCellValue(value) {
  if (typeof value === 'number') {
    return value;
  }

  var normalized = String(value || '')
    .replace(/[$,\s]/g, '')
    .trim();

  if (!normalized) {
    return null;
  }

  if (normalized.charAt(0) === '(' && normalized.charAt(normalized.length - 1) === ')') {
    normalized = '-' + normalized.slice(1, -1);
  }

  var parsed = Number(normalized);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Builds a simple HTML table for email output.
 */
function buildHtmlTable(headers, rows) {
  var html = '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">';
  html += '<tr>';
  headers.forEach(function(header) {
    html += `<th>${escapeHtml(header)}</th>`;
  });
  html += '</tr>';

  rows.forEach(function(row) {
    html += '<tr>';
    row.forEach(function(cell) {
      html += `<td>${escapeHtml(cell)}</td>`;
    });
    html += '</tr>';
  });

  html += '</table>';
  return html;
}

/**
 * Removes blanks and duplicate values while preserving first-seen order.
 */
function uniqueNonEmpty(values) {
  var seen = {};
  return (values || []).filter(function(value) {
    var normalized = String(value || '').trim();
    if (!normalized || seen[normalized]) {
      return false;
    }
    seen[normalized] = true;
    return true;
  });
}

/**
 * Returns true when a header should be excluded from numeric validation.
 */
function isNonIntegerHeader(restaurantInfo, headerTitle) {
  var normalizedTitle = normalizeHeaderName(headerTitle);
  return (restaurantInfo.nonIntegerHeaders || []).some(function(header) {
    return normalizeHeaderName(header) === normalizedTitle;
  });
}

/**
 * Normalizes a value that is expected to be numeric with at most 2 decimal places.
 *
 * Returns:
 * - { status: 'valid' } when the value is already acceptable
 * - { status: 'fixable', fixedValue, fixedDisplayValue } when the value can be safely normalized
 * - { status: 'invalid', reason } when the value should be investigated manually
 *
 * Safe normalization removes formatting noise such as spaces, commas, dollar signs,
 * decimal separators used as punctuation noise, and parentheses for negatives.
 * It also handles patterns like "2($5)" by taking the value inside the parentheses.
 */
function normalizeExpectedIntegerValue(value, displayValue) {
  var decimalTolerance = 0.0000001;

  if (typeof value === 'number') {
    if (Math.abs(value * 100 - Math.round(value * 100)) < decimalTolerance) {
      return { status: 'valid' };
    }
    return { status: 'invalid', reason: 'numeric value has more than 2 decimal places' };
  }

  var rawDisplayValue = String(displayValue != null ? displayValue : value != null ? value : '').trim();
  if (!rawDisplayValue) {
    return { status: 'invalid', reason: 'blank value' };
  }

  if (/^-?\d+(\.\d{1,2})?$/.test(rawDisplayValue)) {
    return { status: 'valid' };
  }

  if (!/^[\d\s,$().-]+$/.test(rawDisplayValue)) {
    return { status: 'invalid', reason: 'contains non-numeric text' };
  }

  var parentheticalAmountMatch = rawDisplayValue.match(/^\s*\d+\s*\(([^)]+)\)\s*$/);
  if (parentheticalAmountMatch) {
    var innerValue = parentheticalAmountMatch[1].trim();
    var innerNormalized = innerValue.replace(/[$,\s]/g, '').replace(/[()]/g, '');
    var innerIsNegative = /^-/.test(innerNormalized);
    innerNormalized = innerNormalized.replace(/^-/, '');

    if ((innerNormalized.match(/\./g) || []).length > 1) {
      innerNormalized = innerNormalized.replace(/\./g, '');
    }

    if (!innerNormalized || !/^\d+(\.\d+)?$/.test(innerNormalized)) {
      return { status: 'invalid', reason: 'no digits found inside parentheses' };
    }

    var innerNumber = Number((innerIsNegative ? '-' : '') + innerNormalized);
    if (isNaN(innerNumber)) {
      return { status: 'invalid', reason: 'could not parse value inside parentheses' };
    }

    if (Math.abs(innerNumber * 100 - Math.round(innerNumber * 100)) >= decimalTolerance) {
      return { status: 'invalid', reason: 'value inside parentheses has more than 2 decimal places' };
    }

    var roundedInnerNumber = Math.round(innerNumber * 100) / 100;
    var roundedInnerToTenth = Math.round(roundedInnerNumber * 10) / 10;
    var innerDisplayDecimals = 0;
    if (Math.abs(roundedInnerNumber - Math.round(roundedInnerNumber)) >= decimalTolerance) {
      innerDisplayDecimals = Math.abs(roundedInnerNumber - roundedInnerToTenth) < decimalTolerance ? 1 : 2;
    }

    return {
      status: 'fixable',
      fixedValue: Math.abs(roundedInnerNumber),
      fixedDisplayValue: Math.abs(roundedInnerNumber).toFixed(innerDisplayDecimals)
    };
  }

  var isNegative = /^\s*-/.test(rawDisplayValue) ||
    /^\s*\(.*\)\s*$/.test(rawDisplayValue);
  var compactValue = rawDisplayValue.replace(/[$,\s]/g, '');
  var numericCandidate = compactValue;
  var decimalMatches = compactValue.match(/\./g) || [];

  if (decimalMatches.length > 1) {
    numericCandidate = compactValue.replace(/\./g, '');
  }

  numericCandidate = numericCandidate.replace(/[()]/g, '');
  if (!numericCandidate || !/^\d+(\.\d+)?$/.test(numericCandidate)) {
    return { status: 'invalid', reason: 'no digits found' };
  }

  var normalizedNumber = Number((isNegative ? '-' : '') + numericCandidate);
  if (isNaN(normalizedNumber)) {
    return { status: 'invalid', reason: 'could not parse normalized number' };
  }

  if (Math.abs(normalizedNumber * 100 - Math.round(normalizedNumber * 100)) >= decimalTolerance) {
    return { status: 'invalid', reason: 'normalized value has more than 2 decimal places' };
  }

  var roundedNumber = Math.round(normalizedNumber * 100) / 100;
  var roundedToTenth = Math.round(roundedNumber * 10) / 10;
  var displayDecimals = 0;
  if (Math.abs(roundedNumber - Math.round(roundedNumber)) >= decimalTolerance) {
    displayDecimals = Math.abs(roundedNumber - roundedToTenth) < decimalTolerance ? 1 : 2;
  }

  return {
    status: 'fixable',
    fixedValue: roundedNumber,
    fixedDisplayValue: roundedNumber.toFixed(displayDecimals)
  };
}

/**
 * Builds the HTML report section for a single restaurant over a provided date window.
 *
 * Responsibilities:
 * - reads sheet data and resolves important columns by header
 * - clears Notes cells containing only "0"
 * - fixes incorrect Day of Week values
 * - collects missing dates, duplicate dates, provider-total issues, non-zero Other Total rows,
 *   numeric fixes, invalid numeric values, missing provider columns, and notes
 * - returns null when there is nothing to report
 */
function buildClosingReportHtml(restaurantName, startDate, endDate) {
  var restaurantInfo = sheetInfo[restaurantName];
  if (!restaurantInfo) return null;

  var formSheet = SpreadsheetApp.openById(restaurantInfo.sheetID).getSheetByName('Form Responses 1');
  var startRow = 2;
  var timeZone = Session.getScriptTimeZone();
  var startDate = new Date(startDate); // inclusive
  var endDate = new Date(endDate); // non-inclusive
  var startDateKey = formatDateKey(startDate, timeZone);
  var endDateKey = formatDateKey(endDate, timeZone);
  var lastRow = formSheet.getLastRow();
  if (lastRow < startRow) return;

  var headerValues = formSheet.getRange(1, 1, 1, formSheet.getLastColumn()).getDisplayValues()[0];
  var dateColumn = getColumnIndexByHeader(headerValues, 'Date of Operation');
  var dayOfWeekColumn = getColumnIndexByHeader(headerValues, 'Day of Week');
  var notesColumn = getColumnIndexByHeaderPrefix(headerValues, 'Notes');
  var employeeColumn = getColumnIndexByHeader(headerValues, 'Employee Name');
  var otherTotalColumn = getColumnIndexByHeader(headerValues, 'Other Total');
  var providerConfigs = restaurantInfo.requiredProviderColumns || [];
  if (dateColumn === -1 || dayOfWeekColumn === -1) {
    throw new Error('Required columns "Date of Operation" and/or "Day of Week" were not found.');
  }

  var rowCount = lastRow - startRow + 1;
  var lastColumn = formSheet.getLastColumn();
  var dateValues = formSheet.getRange(startRow, dateColumn, rowCount, 1).getValues();
  var dayOfWeekRange = formSheet.getRange(startRow, dayOfWeekColumn, rowCount, 1);
  var dayOfWeekValues = dayOfWeekRange.getDisplayValues();
  var notesRange = notesColumn === -1
    ? null
    : formSheet.getRange(startRow, notesColumn, rowCount, 1);
  var notesValues = notesRange
    ? notesRange.getDisplayValues()
    : null;
  var employeeValues = employeeColumn === -1
    ? null
    : formSheet.getRange(startRow, employeeColumn, rowCount, 1).getDisplayValues();
  var otherTotalValues = otherTotalColumn === -1
    ? null
    : formSheet.getRange(startRow, otherTotalColumn, rowCount, 1).getDisplayValues();
  var allDataRange = formSheet.getRange(startRow, 1, rowCount, lastColumn);
  var allDataValues = allDataRange.getValues();
  var allDisplayValues = allDataRange.getDisplayValues();
  var providerColumns = providerConfigs.map(function(providerConfig) {
    return {
      label: providerConfig.label,
      header: providerConfig.header,
      columnIndex: getColumnIndexByHeader(headerValues, providerConfig.header)
    };
  });
  var missingProviderColumns = providerColumns.filter(function(providerColumn) {
    return providerColumn.columnIndex === -1;
  });
  providerColumns = providerColumns.filter(function(providerColumn) {
    return providerColumn.columnIndex !== -1;
  });
  var providerValuesByLabel = {};
  providerColumns.forEach(function(providerColumn) {
    providerValuesByLabel[providerColumn.label] = formSheet
      .getRange(startRow, providerColumn.columnIndex, rowCount, 1)
      .getDisplayValues();
  });
  var dateCounts = {};
  var notesByDate = {};
  var employeesByDate = {};
  var datedNotesRows = [];
  var correctedDayOfWeekRows = [];
  var missingProviderValues = [];
  var nonZeroOtherTotalRows = [];
  var fixedIntegerRows = [];
  var invalidIntegerRows = [];
  var integerColumnsToValidate = headerValues
    .map(function(header, index) {
      return {
        columnIndex: index + 1,
        header: header
      };
    })
    .filter(function(column) {
      return !isNonIntegerHeader(restaurantInfo, column.header);
    });

  dateValues.flat().forEach(function(date, index) {
    if (!(date instanceof Date)) return;

    var dateKey = formatDateKey(date, timeZone);
    if (dateKey < startDateKey || dateKey >= endDateKey) {
      return;
    }

    dateCounts[dateKey] = (dateCounts[dateKey] || 0) + 1;

    if (employeeValues) {
      var employeeName = String(employeeValues[index][0] || '').trim();
      if (employeeName) {
        employeesByDate[dateKey] = employeesByDate[dateKey] || [];
        employeesByDate[dateKey].push(employeeName);
      }
    }

    if (notesValues) {
      var noteValue = String(notesValues[index][0] || '').trim();
      if (noteValue === '0') {
        notesValues[index][0] = '';
        noteValue = '';
      }
      if (noteValue) {
        notesByDate[dateKey] = notesByDate[dateKey] || [];
        if (notesByDate[dateKey].indexOf(noteValue) === -1) {
          notesByDate[dateKey].push(noteValue);
        }
        datedNotesRows.push({
          date: formatDisplayDate(date, timeZone),
          dateKey: dateKey,
          employeeName: employeeValues ? String(employeeValues[index][0] || '').trim() : '',
          note: noteValue
        });
      }
    }

    var expectedDay = getExpectedDayOfWeek(date, timeZone);
    var currentDay = String(dayOfWeekValues[index][0] || '').trim();
    if (currentDay !== expectedDay) {
      dayOfWeekValues[index][0] = expectedDay;
      correctedDayOfWeekRows.push({
        date: formatDisplayDate(date, timeZone),
        dateKey: dateKey,
        previousValue: currentDay || '(blank)',
        updatedValue: expectedDay
      });
    }

    integerColumnsToValidate.forEach(function(column) {
      var rowValue = allDataValues[index][column.columnIndex - 1];
      var rowDisplayValue = allDisplayValues[index][column.columnIndex - 1];
      var integerCheck = normalizeExpectedIntegerValue(rowValue, rowDisplayValue);

      if (integerCheck.status === 'fixable') {
        allDataValues[index][column.columnIndex - 1] = integerCheck.fixedValue;
        fixedIntegerRows.push({
          date: formatDisplayDate(date, timeZone),
          employeeName: employeeValues ? String(employeeValues[index][0] || '').trim() : '',
          columnName: String(column.header || '').trim(),
          originalValue: String(rowDisplayValue || '').trim(),
          fixedValue: integerCheck.fixedDisplayValue
        });
      } else if (integerCheck.status === 'invalid' && integerCheck.reason !== 'blank value') {
        invalidIntegerRows.push({
          date: formatDisplayDate(date, timeZone),
          employeeName: employeeValues ? String(employeeValues[index][0] || '').trim() : '',
          columnName: String(column.header || '').trim(),
          originalValue: String(rowDisplayValue || '').trim(),
          reason: integerCheck.reason
        });
      }
    });

    var missingProvidersForRow = [];
    providerColumns.forEach(function(providerColumn) {
      var providerCellValue = providerValuesByLabel[providerColumn.label][index][0];
      var numericValue = parseNumericCellValue(providerCellValue);
      if (numericValue === null || numericValue === 0) {
        missingProvidersForRow.push(providerColumn.label);
      }
    });

    if (missingProvidersForRow.length !== 0) {
      missingProviderValues.push({
        date: formatDisplayDate(date, timeZone),
        dateKey: dateKey,
        employeeNames: uniqueNonEmpty(employeesByDate[dateKey] || []),
        providers: missingProvidersForRow
      });
    }

    if (otherTotalValues) {
      var otherTotalRawValue = otherTotalValues[index][0];
      var otherTotalNumericValue = parseNumericCellValue(otherTotalRawValue);
      if (otherTotalNumericValue !== null && otherTotalNumericValue !== 0) {
        nonZeroOtherTotalRows.push({
          date: formatDisplayDate(date, timeZone),
          dateKey: dateKey,
          employeeName: employeeValues ? String(employeeValues[index][0] || '').trim() : '',
          otherTotalValue: String(otherTotalRawValue || '').trim()
        });
      }
    }
  });

  if (fixedIntegerRows.length !== 0) {
    allDataRange.setValues(allDataValues);
  }

  if (correctedDayOfWeekRows.length !== 0) {
    dayOfWeekRange.setValues(dayOfWeekValues);
  }

  if (notesRange) {
    notesRange.setValues(notesValues);
  }

  var missingDates = [];
  var duplicateDates = [];

  for (var d = new Date(startDate); d < endDate; d.setDate(d.getDate() + 1)) {
    var formattedDate = formatDateKey(d, timeZone);
    var count = dateCounts[formattedDate] || 0;

    if (count === 0) {
      missingDates.push(formatDisplayDate(d, timeZone));
    } else if (count > 1) {
      duplicateDates.push({
        date: formatDisplayDate(d, timeZone),
        dateKey: formattedDate,
        count: count
      });
    }
  }

  if (missingDates.length === 0 && duplicateDates.length === 0 && correctedDayOfWeekRows.length === 0 && missingProviderValues.length === 0 && nonZeroOtherTotalRows.length === 0 && fixedIntegerRows.length === 0 && invalidIntegerRows.length === 0 && missingProviderColumns.length === 0 && datedNotesRows.length === 0) {
    return null;
  }

  var formUrl = restaurantInfo.formUrl;
  var htmlBody = `<h2>${restaurantName}</h2>`;
  htmlBody += `<p>Closing report check reviewed Date of Operation values from ${formatDisplayDate(startDate, timeZone)} through ${formatDisplayDate(new Date(endDate.getTime() - 86400000), timeZone)}.</p>`;

  if (missingDates.length !== 0) {
    htmlBody += '<h3>Missing Dates</h3>';
    htmlBody += `<p>The following ${restaurantName} closing dates are missing:</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation'],
      missingDates.map(function(date) {
        return [date];
      })
    );
  }

  if (duplicateDates.length !== 0) {
    htmlBody += '<h3>Duplicate Record Dates</h3>';
    htmlBody += `<p>The following ${restaurantName} closing dates have multiple records and should only have one row each:</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Record Count', 'Employee Name(s)', 'Notes'],
      duplicateDates.map(function(entry) {
        var notes = notesByDate[entry.dateKey] || [];
        var employeeNames = uniqueNonEmpty(employeesByDate[entry.dateKey] || []);
        return [
          entry.date,
          String(entry.count),
          employeeNames.join(' | '),
          notes.join(' | ')
        ];
      })
    );
  }

  if (correctedDayOfWeekRows.length !== 0) {
    htmlBody += '<h3>Day Of Week Corrections</h3>';
    htmlBody += `<p>The following ${restaurantName} Day of Week values were corrected to match the Date of Operation:</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Previous Day', 'Correct Day', 'Notes'],
      correctedDayOfWeekRows.map(function(entry) {
        var notes = notesByDate[entry.dateKey] || [];
        return [
          entry.date,
          entry.previousValue,
          entry.updatedValue,
          notes.join(' | ')
        ];
      })
    );
  }

  if (missingProviderValues.length !== 0) {
    htmlBody += '<h3>Missing Provider Totals</h3>';
    htmlBody += `<p>The following ${restaurantName} closing dates have provider totals that are blank or zero and should be reviewed:</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Employee Name(s)', 'Missing Provider Totals', 'Notes'],
      missingProviderValues.map(function(entry) {
        var notes = notesByDate[entry.dateKey] || [];
        return [
          entry.date,
          entry.employeeNames.join(' | '),
          entry.providers.join(', '),
          notes.join(' | ')
        ];
      })
    );
  }

  if (nonZeroOtherTotalRows.length !== 0) {
    htmlBody += '<h3>Non-Zero Other Total</h3>';
    htmlBody += `<p>The following ${restaurantName} closing dates have a non-zero Other Total. This may mean another report column should be added.</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Employee Name', 'Other Total', 'Notes'],
      nonZeroOtherTotalRows.map(function(entry) {
        var notes = notesByDate[entry.dateKey] || [];
        return [
          entry.date,
          entry.employeeName,
          entry.otherTotalValue,
          notes.join(' | ')
        ];
      })
    );
  }

  if (fixedIntegerRows.length !== 0) {
    htmlBody += '<h3>Fixed Numeric Values</h3>';
    htmlBody += `<p>The following ${restaurantName} values were expected to be numeric with up to 2 decimal places and were automatically fixed in the sheet.</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Employee Name', 'Column', 'Original Value', 'Fixed Value'],
      fixedIntegerRows.map(function(entry) {
        return [
          entry.date,
          entry.employeeName,
          entry.columnName,
          entry.originalValue,
          entry.fixedValue
        ];
      })
    );
  }

  if (invalidIntegerRows.length !== 0) {
    htmlBody += '<h3>Invalid Numeric Values</h3>';
    htmlBody += `<p>The following ${restaurantName} values were expected to be numeric with up to 2 decimal places but could not be safely fixed and should be investigated.</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Employee Name', 'Column', 'Original Value', 'Issue'],
      invalidIntegerRows.map(function(entry) {
        return [
          entry.date,
          entry.employeeName,
          entry.columnName,
          entry.originalValue,
          entry.reason
        ];
      })
    );
  }

  if (missingProviderColumns.length !== 0) {
    htmlBody += '<h3>Missing Provider Columns</h3>';
    htmlBody += `<p>The following required provider total columns were not found in the ${restaurantName} sheet:</p>`;
    htmlBody += buildHtmlTable(
      ['Missing Column Header'],
      missingProviderColumns.map(function(providerColumn) {
        return [providerColumn.header];
      })
    );
  }

  if (datedNotesRows.length !== 0) {
    htmlBody += '<h3>Notes</h3>';
    htmlBody += `<p>The following ${restaurantName} closing dates have notes:</p>`;
    htmlBody += buildHtmlTable(
      ['Date of Operation', 'Employee Name', 'Notes'],
      datedNotesRows.map(function(entry) {
        return [entry.date, entry.employeeName, entry.note];
      })
    );
  }

  if (missingDates.length !== 0 || duplicateDates.length !== 0) {
    htmlBody += `<p>Please fill out <a href="${formUrl}">this form</a> to address the missing dates.</p>`;
  }

  return htmlBody;
}

/**
 * Sends a report email for a single restaurant for the provided date window.
 */
function checkClosingReports(restaurantName, startDate, endDate, reportLabel) {
  var restaurantInfo = sheetInfo[restaurantName];
  if (!restaurantInfo) return;

  var htmlBody = buildClosingReportHtml(restaurantName, startDate, endDate);
  if (!htmlBody) return;

  MailApp.sendEmail({
      to: restaurantInfo.emailID,
      subject: `${reportLabel || 'Closing Report'} - ${restaurantName} Closing Report Issues`,
      htmlBody: htmlBody
  });
}

/**
 * Sends one combined email containing all restaurant sections that have issues.
 * Each restaurant section is separated with <hr>.
 */
function checkCombinedClosingReports(startDate, endDate, reportLabel) {
  var sections = [];
  var recipients = [];

  Object.keys(sheetInfo).forEach(function(restaurantName) {
    var htmlBody = buildClosingReportHtml(restaurantName, startDate, endDate);
    if (htmlBody) {
      sections.push(htmlBody);
      recipients = recipients.concat(
        String(sheetInfo[restaurantName].emailID || '')
          .split(',')
          .map(function(email) { return email.trim(); })
          .filter(function(email) { return email; })
      );
    }
  });

  if (sections.length === 0) return;

  var uniqueRecipients = recipients.filter(function(email, index) {
    return recipients.indexOf(email) === index;
  });

  MailApp.sendEmail({
    to: uniqueRecipients.join(', '),
    subject: `${reportLabel || 'Closing Report'} - Combined Closing Report Issues`,
    htmlBody: sections.join('<hr>')
  });
}

/**
 * Daily Ameci check for the last 7 completed Date of Operation days.
 */
function checkAmeciClosingReportsDaily() {
  var restaurantName = 'Ameci';
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  var startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 7); // Check the last 7 completed operation dates
  checkClosingReports(restaurantName, startDate, endDate, 'Daily');
}

/**
 * Monthly Ameci check for the previous full calendar month.
 */
function checkAmeciClosingReportsMonthly() {
  var restaurantName = 'Ameci';
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  endDate = new Date(endDate.getFullYear(), endDate.getMonth(), 1); // start of current month
  var startDate = new Date(endDate.getFullYear(), endDate.getMonth() - 1, 1); // start of previous month
  checkClosingReports(restaurantName, startDate, endDate, 'Monthly');
}

/**
 * Daily Aroma check for the last 7 completed Date of Operation days.
 */
function checkAromaClosingReportsDaily() {
  var restaurantName = 'Aroma';
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  var startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 7); // Check the last 7 completed operation dates
  checkClosingReports(restaurantName, startDate, endDate, 'Daily');
}

/**
 * Monthly Aroma check for the previous full calendar month.
 */
function checkAromaClosingReportsMonthly() {
  var restaurantName = 'Aroma';
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  endDate = new Date(endDate.getFullYear(), endDate.getMonth(), 1); // start of current month
  var startDate = new Date(endDate.getFullYear(), endDate.getMonth() - 1, 1); // start of previous month
  checkClosingReports(restaurantName, startDate, endDate, 'Monthly');
}

/**
 * Daily combined Ameci + Aroma check for the last 7 completed Date of Operation days.
 */
function checkCombinedClosingReportsDaily() {
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  var startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 7);
  checkCombinedClosingReports(startDate, endDate, 'Daily');
}

/**
 * Monthly combined Ameci + Aroma check for the previous full calendar month.
 */
function checkCombinedClosingReportsMonthly() {
  var timeZone = Session.getScriptTimeZone();
  var endDate = getStartOfToday(timeZone);
  endDate = new Date(endDate.getFullYear(), endDate.getMonth(), 1);
  var startDate = new Date(endDate.getFullYear(), endDate.getMonth() - 1, 1);
  checkCombinedClosingReports(startDate, endDate, 'Monthly');
}
