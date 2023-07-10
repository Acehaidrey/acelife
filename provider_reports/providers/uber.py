import requests
import json
from flask import Flask, request

app = Flask(__name__)

# curl -X POST -F 'client_id=M5VQfGY4x9BjyeOg2XqYQ7cp9xSiHZEp'\
#       -F 'client_secret=I7yiL6txSOB0vdR0goWb0PY6BTCphFKTJtE7jvWP'\
#       -F 'grant_type=client_credentials'\
#       -F 'scope="eats.report"'\
#       "https://login.uber.com/oauth/v2/token"


# Replace 'YOUR_ACCESS_TOKEN' with your actual access token or API key
access_token = 'IA.VUNmGAAAAAAAEgASAAAABwAIAAwAAAAAAAAAEgAAAAAAAAGMAAAAFAAAAAAADgAQAAQAAAAIAAwAAAAOAAAAYAAAABwAAAAEAAAAEAAAADSrb1HEuG2qVCI3GPVp7ho8AAAAKM_NAgj-aztR4mXZXWjhwiG_Grs5ySlyAxX1qt8Gs4qKnBEpEyAuSy1zQc06rdnppCzbZYqEQXNjtwd2DAAAAChSXVVRf3eBYFRD5SQAAABiMGQ4NTgwMy0zOGEwLTQyYjMtODA2ZS03YTRjZjhlMTk2ZWU'

# Endpoint URL for creating a report
url = 'https://api.uber.com/v1/eats/report'
# stores = 'https://api.uber.com/v1/eats/stores'

# Request payload for creating the report
# payload = {
#     'report_type': 'PAYMENT_DETAILS_REPORT',
#     'start_date': '2023-06-01',
#     'end_date': '2023-06-30',
#     'store_uuids': ['22275bd0-5e5a-4d89-b68e-e9d900b41701']  # ['3f351e05-fc5c-4bc6-ab9e-1a18e1f26362']
# }
#
# headers = {
#     'Authorization': f'Bearer {access_token}',
#     'Content-Type': 'application/json',
# }
#
# # Send POST request to create the report
# # response = requests.post(stores, headers=headers)
# # print(response)
# response = requests.post(url, headers=headers, data=json.dumps(payload))
#
# # Check the response status code
# if response.status_code == 200:
#     report_data = response.json()
#     print(report_data)
#     # Handle the report data as per your requirements
#     print(f"Report created successfully. Report ID: {report_data['workflow_id']}")
# else:
#     print(f"Failed to create report. Error: {response.text}")
#


@app.route('/')
def index():
    return 'ok'

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    webhook_data = request.get_json()
    print(webhook_data)

    # Verify the authenticity of the webhook request
    # Implement your signature validation logic here

    # Handle the webhook event
    event_type = webhook_data.get('event_type')

    if event_type == 'eats.report.success':
        # Handle the report success event
        report_metadata = webhook_data.get('report_metadata')
        # Extract relevant information from report_metadata and process as needed
        # For example, download the report using the provided download URL

        # Acknowledge receipt of the webhook event
        return '', 200

    # For other event types, handle accordingly

    # Return a response for unsupported event types
    return '', 204


def create_report():
    # Your code to create the report using POST /eats/reports
    # Replace the placeholders with your actual report creation logic
    url = 'https://api.uber.com/v1/eats/report'
    payload = {
        'report_type': 'PAYMENT_DETAILS_REPORT',
        'start_date': '2023-06-01',
        'end_date': '2023-06-30',
        'store_uuids': ['22275bd0-5e5a-4d89-b68e-e9d900b41701']  # ['3f351e05-fc5c-4bc6-ab9e-1a18e1f26362']
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    # Send POST request to create the report
    response = requests.post(url, headers=headers, data=json.dumps(payload))

    # Check the response status code
    if response.status_code == 200:
        report_data = response.json()
        workflow_id = report_data['workflow_id']

        # Print the workflow_id for reference
        print(f"Report created successfully. Workflow ID: {workflow_id}")

        # Implement your webhook setup logic here
        # Register the webhook endpoint with Uber Eats API using the appropriate workflow_id

        # Start the Flask server to handle webhook notifications
        app.run()
    else:
        print(f"Failed to create report. Error: {response.text}")


if __name__ == '__main__':
    create_report()
