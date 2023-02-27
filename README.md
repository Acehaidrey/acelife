# AceLife

This repository will be a mosh posh of projects, files scripts that are owned by me to help me in my everyday life.

## Project 1: Customer Information Aggregation

For our pizza shops, [Aroma](http://aromapizzaandpasta.com/) and [Ameci](http://amecilakeforest.com/), 
we have gathered a lot of customer information over the years. We have many different partners that we will pull the data from.
This list includes:
- BeyondMenu
- Brygid
- Doordash
- Eatstreet
- Grubhub
- Menufy
- Menustar
- Slice
- Speedline
- Toast

We get this customer information in specific ways - some will allow us to export scripts, and some will require to parse emails.

For the email parsing, there is some setup (gmail based):
1. Setup google rules to add a label to the orders coming in: Slice, Grubhub etc. You can do this by setting up filter rules.
2. Go to https://takeout.google.com/settings/takeout.
3. Deselect all services except Gmail.
4. Click on "All data included" and select "Deselect all".
5. Select "Mail" and choose the desired export format.
6. Click on "Deselect All" and select the *labels* for the emails you want to download.
7. Click on "All data included" and select the maximum number of emails you want to download (up to 50,000).
8. Click on "Multiple formats".
9. Click on "Create export".
10. Wait for Google to prepare your export. This can take a while depending on the amount of data you've selected.
11. Download the export file and extract the contents to access your Gmail emails. This will provide an MBOX file that will need parsing.
12. The file will need to be unziped.
13. Setup this rule to automatically run every 2 months.

That is now getting the files ready. We then need to setup the rules to create a cron job here to run every day.
1. Check the cron job - it will run everyday to check if files were downloaded and then process them

The cron job will kick off our script. There are both js and python files here operating to process the files, to extract customer info.
Once that happens, then we create outputted JSON files:
1. Transaction information JSON
2. Error information JSON
3. Summarized customer information JSON

- For Brygid, we need to go to the site to login and download the customer info from the site.
- For Toast, we need to go to the site to login and download the customer info from this site. It does not give address info.
- For Speedline, we need to call them to get a csv of our customer export.
- For Menufy, we need to download the customer info files for email and delivery respectively.

All the above files need to be added to the Reports/POS folder. The execute.js script logic can shed more insight on what is happening.


Additional project details can be found [here](https://docs.google.com/document/d/1SY-x9IjD4EF6XFukgUbjEhsaYp_CBOY1gGCEC3FQk6c/edit?usp=sharing).

Example commands:
- BeyondMenu: Currently not supported since the email do not have the content for order info
- Brygid: `./main.js -i ./Reports/POS/Brygid-2023-02-01.csv -o Brygid`
- Doordash: `./main.js -i ./Reports/Takeout/Mail/Orders-Doordash.mbox -o Doordash`
- Eatstreet: `./main.js -i ./Reports/Takeout/Mail/Orders-Eatstreet.mbox -o Eatstreet`
- Grubhub: `./main.js -i ./Reports/Takeout/Mail/Orders-Grubhub.mbox -o Grubhub`
- Menufy: `./main.js -d ./Reports/Customer_Delivery_Addresses_02-13-2023-Aroma.csv -e ./Reports/Customer_Emails_02-13-2023-Aroma.csv -o Menufy`
- Menustar: `./main.js -i ./Reports/Takeout/Mail/Orders-Menustar.mbox -o Menustar`
- Slice: `./main.js -i ./Reports/Takeout/Mail/Orders-Slice.mbox -o Slice`
- Speedline: `./main.js -i ./Reports/POS/Speedline-2023-02-01.csv -o Speedline`
- Toast: `./main.js -i -e ./Reports/Takeout/Mail/Orders-Toast.mbox ./Reports/POS/Toast-2023-02-01.csv -o Toast`