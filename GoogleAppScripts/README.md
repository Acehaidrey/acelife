
## Google App Scripts

Throughout being a small business owner, we have found numerous task as mundane and frankly tasks that can be automated with some
special setup. These google app scripts are used as orders protocol are generally used to email the order to our system.

### Auto Order Error Charges Contest

We have four main partners for ordering:

- UberEats (Weekly Report)
- Grubhub (Daily Report)
- Slice (Error Charge From Order)
- Doordash (To be implemented)

Each has their own way of notifying us of error charges, but we setup scripts to see the daily/weekly sales report (respective to partner), setup a scheduled job here to parse the error orders, additional information, and send an adjustment email as necessary to the respective support teams.

TODO: More details about this need to be placed about each script. Mention how can't have any 
overlapping function names or variables for stand off script. Need to package a lib to properly do so.

### Clean Up Scripts

These are a series of functional routines to help organization processes be automated.

- Automate deleting archived emails before a certain date that does not contain any custom labels nor any responses
- Automate archiving messages for given labels I have assumed
