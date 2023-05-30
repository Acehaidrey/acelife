const folderName = "BusinessFinances";

/**
 * Create folder structure for the BusinessFinances folder where we will keep all store reports.
 */
function createYearFolders() {
  var parentFolder = DriveApp.getFoldersByName(folderName).next();
  var subfolders = parentFolder.getFolders();
  
  while (subfolders.hasNext()) {
    var subfolder = subfolders.next();
    var subfolderName = subfolder.getName();
    
    if (subfolderName === "Aroma" || subfolderName === "Ameci") {
      var year = new Date().getFullYear();
      var years = [year, year - 1, year - 2, year - 3, year - 4]; // From this year to 2019
      var months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
      
      years.forEach(function(year) {
        var yearFolder = createOrGetFolder(subfolder, year);
        
        months.forEach(function(month) {
          createOrGetFolder(yearFolder, month);
        });
      });
    }
  }
}

function createOrGetFolder(parent, name) {
  var folders = parent.getFoldersByName(name);
  var folder;
  
  if (folders.hasNext()) {
    folder = folders.next();
  } else {
    folder = parent.createFolder(name);
  }
  
  return folder;
}
