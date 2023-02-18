#!/usr/bin/env node

const Papa = require('papaparse');
const fs = require('fs');


function combineCSVFiles(file1, file2, storeName) {
  let data1 = [];
  let data2 = [];
  let data1Records = [];
  let data2Records = [];

  return new Promise((resolve, reject) => {
    fs.readFile(file1, 'utf8', (err, fileContents) => {
      if (err) {
        reject(err);
      }

      data1 = Papa.parse(fileContents, { header: true }).data;
	  data1.forEach(row1 => {
		  const combinedRecord = {
			  store: storeName,
			  customerNames: [row1['First Name'] + ' ' + row1['Last Name']],
			  customerNumber: row1['Phone'],
			  lastOrderDate: null,
			  firstOrderDate: null,
			  customerAddresses: [row1['Address1'] + ', ' + row1['City'] + ', ' + row1['State'] + ' ' + row1['ZipCode']],
			  customerEmails: [],
			  orderCount: 0,
			  totalSpend: 0,
			};
		  data1Records.push(combinedRecord);
	  });
	  data1 = data1Records;


	  console.log(file1)
	  console.log(fileContents)
	  console.log(data1)

      fs.readFile(file2, 'utf8', (err, fileContents) => {
        if (err) {
          reject(err);
        }

        data2 = Papa.parse(fileContents, { header: true }).data;
		data2.forEach(row1 => {
		  const combinedRecord = {
			  store: storeName,
			  customerNames: [row1['First Name'] + ' ' + row1['Last Name']],
			  customerNumber: null,
			  lastOrderDate: row1['Last Order Date'],
			  firstOrderDate: row1['First Order Date'],
			  customerAddresses:  [],
			  customerEmails: [row1['Email']],
			  orderCount: 0,
			  totalSpend: 0,
			};
		  data2Records.push(combinedRecord);
	  });
	  data2 = data2Records;

		console.log(file2)
		  console.log(fileContents)
		  console.log(data2)

        const combinedData = [];
        data1.forEach(row1 => {
          data2.forEach(row2 => {
            if (row1['First Name'] === row2['First Name'] && row1['Last Name'] === row2['Last Name']) {
              combinedData.push({ ...row1, ...row2 });
            }
          });
        });

        resolve(combinedData);
      });
    });
  });
}


let f2 = '/Users/ahaidrey/Downloads/Customer_Emails_02-13-2023-Aroma.csv'
let f1 = '/Users/ahaidrey/Downloads/Customer_Delivery_Addresses_02-13-2023-Aroma.csv'
combineCSVFiles(f1, f2, 'Aroma')