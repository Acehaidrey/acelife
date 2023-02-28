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

Additional project details can be found [here](https://docs.google.com/document/d/1SY-x9IjD4EF6XFukgUbjEhsaYp_CBOY1gGCEC3FQk6c/edit?usp=sharing).


### Prerequisites

#### Node Application

This is a node application so need to make sure node and npm are installed. Make sure that Node.js and npm are installed on your machine. You can download and install them from the official Node.js website: https://nodejs.org/en/download/. Then run `npm install` in the project folder of `customerInfoCollection`.

#### Setup Email Downloads

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
13. Setup this rule to automatically run every 2 months. See if we can make this more frequent.

#### Application Specific Password
In order to setup for gmail a password to run the execution, you cannot use your regular password.
If you're using Gmail as your email service, you can generate an application-specific password by following these steps:

1. Go to your Google Account page.
2. Click on the "Security" tab.
3. Scroll down to the "Signing in to Google" section.
4. Click on "App passwords".
5. Select the app and device you want to generate the app password for.

Follow the instructions to generate and use the app password.
Once you have generated an application-specific password, you can use it in place of your regular password when sending email using a third-party application like Node.js. Be sure to update your email configuration settings with the new password.

#### Other Inputs - POS & Other Customer CSV Files

- For Brygid, we need to go to the site to login and download the customer info from the site.
- For Toast, we need to go to the site to login and download the customer info from this site. It does not give address info.
- For Speedline, we need to call them to get a csv of our customer export.
- For Menufy, we need to download the customer info files for email and delivery respectively.

All the above files need to be added to the Reports/POS folder. The execute.js script logic can shed more insight on what is happening.

#### Scheduled Invocation

That is now getting the files ready to process. We then need to setup the rules to create a cron job here to run every day.
1. Check the cron job - it will run everyday to check if files were downloaded and then process them.
2. To set up a cron job on your Mac to run daily, you can use the crontab command. Here's an example of how to create a cron job that runs a script every day at 9am:
3. Open the Terminal app on your Mac.
4. Type the following command to open the crontab editor: `crontab -e`
5. If this is the first time you are using crontab, you may be prompted to choose an editor. Select your preferred editor.
6. In the editor, add the following line: `0 9 * * * EMAIL_PASSWORD=YOUR_PASSWORD ./execute.js`

### Outputs

The cron job will kick off our script. There are both js and python files here operating to process the files, to extract customer info.
Once that happens, then we create outputted JSON files:
1. Transaction information JSON
2. Error information JSON (suffixed with -errors.json)
3. Summarized customer information JSON (suffixed with -customers.json)

### Individual File Processing Commands

Example commands:
- BeyondMenu: Currently not supported since the email do not have the content for order info
- Brygid: `./main.js -i ./Reports/POS/Brygid-2023-02-01.csv -o Brygid`
- Doordash: `./main.js -i ./Reports/Takeout/Mail/Orders-Doordash.mbox -o Doordash`
- Eatstreet: `./main.js -i ./Reports/Takeout/Mail/Orders-Eatstreet.mbox -o Eatstreet`
- Grubhub: `./main.js -i ./Reports/Takeout/Mail/Orders-Grubhub.mbox -o Grubhub`
- Menufy: `./main.js -i ./Reports/Takeout/Mail/Orders-Menufy.mbox -o Menufy`
- Menustar: `./main.js -i ./Reports/Takeout/Mail/Orders-Menustar.mbox -o Menustar`
- Slice: `./main.js -i ./Reports/Takeout/Mail/Orders-Slice.mbox -o Slice`
- Speedline: `./main.js -i ./Reports/POS/Speedline-2023-02-01.csv -o Speedline`
- Toast: `./main.js -i ./Reports/Takeout/Mail/Orders-Toast.mbox -e ./Reports/POS/Toast-2023-02-01.csv -o Toast`

The full end to end invocation where we find the `EMAIL_PASSWORD=YOUR_PASSWORD ./execute.js -n 1`. Where the `n` flag is to identify how many days to look back to find the takeout download file.

### Caveats
- This data set prioritizes the customer phone number and the store. Most unique keys are split by phone and store.
- This means there can be duplicate names, emails, and addresses based off of that information.
- We remove similar names/addresses in order to reduce some noise and arbitrarily pick one of the values of the matches.

### Future Work
- Parse the Menufy transaction emails vs the customer records
- Parse the Grubhub attachements to get total spend info
- Place a state here to the script execution
- Harden this pipeline more.
- Refactor string parsing for leveraging DOM objects parsing