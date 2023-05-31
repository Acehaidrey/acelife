## Automating Report Downloading

Throughout being a small business owner, we have found numerous task as mundane and frankly tasks that can be automated with some
special setup. These financial reports of our partnerships need to be automated to be downloaded, reformatted, validated and merged
into our master datasets to have a good understanding of how our business is performing.

### Project Structure

The project structure is as follows (more or less):
```css
provider_reports/
├── main.py
├── providers/
│   ├── base_provider.py
│   ├── brygid.py
│   ├── eatstreet.py
│   ├── doordash.py
│   ├── menufy.py
│   └── ...
├── reports/
│   ├── menufy_orders_raw_file_downlaoded.csv
│   └── ...
├── processed_reports/
│   ├── menufy_aroma_orders_processed_files.csv
│   └── ...
├── credentials/
│   ├── brygid_credentials.json
│   ├── eatstreet_credentials.json
│   ├── doordash_credentials.json
│   └── ...
├── utils/
│   ├── constants.py
│   ├── general_utils.py
│   ├── uploading_utils.py
│   ├── validation_utils.py
│   └── ...
└── requirements.txt
```
This structure will allow us to extend as the project grows more.

#### Credential Files

To safely provide credential information we must separate out these secret information
in a way to easily plug and play too. We don't go overkill by storing in vault etc.
but create simple json files of the following format.
We specify the store this credentials belongs to as a provider can have multiple
different logins or even the same (we then input same info twice with different store names).

```css
{
  "stores": [
    {
      "name": "Aroma",
      "username": "admin@aromapizzaandpasta.com",
      "password": "ABC123"
    },
    {
      "name": "Ameci",
      "username": "admin@amecilakeforest.com",
      "password": "DEF456"
    }
  ]
}

```

The provider file expects this credential file name as an input.

#### Base Provider

The base provider here is the blueprint of how the provider scripts are expected to operate.
Each provider will have order information but additionally can have information about customers.

```css
    The expected lifecycle interaction with this class is:
                        login()
                        preprocess_reports()
                        get_reports()
                        postprocess_reports()
                        validate_reports()
                        upload_reports()
                        quit()
```
Where the `get_reports` call can be multiple reports, namely:
```css
                        get_orders()
                        get_customers()
```
Therefore we must implement at least `get_orders`.

The extensibility is to either through selenium actions to get the reports or it can be via an API.
Both are acceptable but majority do not offer an API to customers.

For now, see any classes `main.py` function in the providers/ endpoint.

#### Entry Point

The `main.py` function will invoke these providers for any provider file passed but it must be added to `provider_map`.
This will handle all the orchestration.

In here we have a few options to filter what we would like to run:

| Argument Flag    | Default Value         | Description                                                                                        |
|------------------|-----------------------|----------------------------------------------------------------------------------------------------| 
| -s, --start-date | Required              | Can be of form 2023/01/15 or of form 2023/01 which will then set 1 as the default day.             |
| -e, --end-date   | Required              | Can be of form 2023/01/28 or of form 2023/01 which will then set last day of month as default day. |
| -c, --cleanup    | False                 | Delete all raw report files in reports/ directory.                                                 |
| -p, --providers  | All in Providers Enum | Space separated list of providers to run report for (i.e. doordash, ubereats, etc.)                |
| -n, --stores     | All in Stores Enum    | Space separated list of store names to run report for (i.e. aroma, ameci)                          |

Running a command such as
`python main.py -s 2023/03 -e 2023/03 -p office_express -n ameci`
will invoke the script for the full month of March 2023 for the provider of office_express for Ameci only.


#### Raw & Processed Reports

The idea is that we download the reports initially to `reports/` directory and then
we format the information within them, create consolidated reports, separate out rows per lcoation
and do any additional post processing such as converting to csv files from other formats, and 
handling that to place files in the `reports_processed/` directory.

#### Reports Status Tracker & Future Work

| Provider       | Status          | Blockers / Notes                                                             |
|----------------|-----------------|------------------------------------------------------------------------------| 
| Brygid         | DONE            | Download customer info after order info.                                     |
| Eatstreet      | DONE            | Convert html download to csv to take transaction info only.                  |
| Future Foods   | IN PROGRESS     | Issues with datepicker code                                                  |
| Grubhub        | BLOCKED         | Knows its an automated script requiring captcha. NO API available.           |
| Menufy         | DONE            | Donwload order, del info, and customer email info and combine customer info. |
| Office Express | DONE            | Both stores same login. One download & separate out orders per location.     |
| Doordash       | NOT YET STARTED | Need to download order info, drive info, error info, & cancelled info.       |
| UberEats       | NOT YET STARTED | Need to download order info, error info, & cancelled info.                   |
| Slice          | NOT YET STARTED | Need to download order info pdf and get info exported from there.            |
| Toast          | NOT YET STARTED | Need to download order info, customer info, and payment info.                |
| Vantiv         | NOT YET STARTED | Need to get merchant processing statements.                                  |

These providers need to be finished and then there are some providers who we handle
using google app scripts as they send over info via emails. Consider to build around those here.

Then we need to push this info ultimately to google drive. We have utils in place to accomplish this.

Lastly we need to push to GCP to process and persist this information to interact with and build 
dashboards on top of.
