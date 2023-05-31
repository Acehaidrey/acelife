import requests

# Set your access token
access_token = 'YOUR_ACCESS_TOKEN'

# Set the start and end dates
start_date = '2023-05-01'
end_date = '2023-05-31'

# Construct the API endpoint URL
url = f'https://api.pos.toasttab.com/v2/orders?startDate={start_date}&endDate={end_date}'

# Set the headers with the access token
headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

# Send the GET request to retrieve the orders
response = requests.get(url, headers=headers)

# Check if the request was successful (status code 200)
if response.status_code == 200:
    orders = response.json()['orders']
    # Process the retrieved orders as needed
    for order in orders:
        # Extract relevant information from the order
        order_id = order['id']
        order_date = order['closedAt']
        # Process and use the order data as needed
        print(f"Order ID: {order_id}, Date: {order_date}")
else:
    # Handle the case where the request was not successful
    print(f"Request failed with status code {response.status_code}")
