import os
import googleapiclient
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# OAuth scopes required for accessing Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']


def authenticate():
    """
    Authenticates the user and returns the credentials.

    This function authenticates the user using OAuth 2.0 and returns the credentials
    required for accessing Google Drive.

    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials.
    """
    creds = None
    credential_file_path = os.path.abspath('../credentials/google_client_secret.json')
    if os.path.exists(credential_file_path):
        try:
            creds = Credentials.from_authorized_user_file(credential_file_path, SCOPES)
            print(creds)
        except ValueError as e:
            print(f'Error getting credential file: {e}')

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credential_file_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(credential_file_path, 'w') as token:
            token.write(creds.to_json())

    return creds


def upload_file(credentials, local_file_path):
    """
    Uploads a file to Google Drive.

    This function uploads a file to Google Drive using the provided credentials.

    Args:
        credentials (google.oauth2.credentials.Credentials): The authenticated credentials.
        local_file_path (str): The local file path of the file to be uploaded.
    """
    drive_service = build('drive', 'v3', credentials=credentials)

    folder_id = '13ywSybs8Y34Sx1dVCAwAluLztE-19vjc'
    file_name = os.path.basename(local_file_path)
    metadata = {'name': file_name, 'parents': [folder_id]}
    media_body = googleapiclient.http.MediaFileUpload(local_file_path)
    file = drive_service.files().create(body=metadata, media_body=media_body).execute()

    print('File uploaded successfully.')
    print('File ID:', file.get('id'))
    print('View online:', 'https://drive.google.com/file/d/' + file.get('id') + '/view')


if __name__ == '__main__':
    # Authenticate and upload the file
    credentials = authenticate()
    upload_file(credentials, 'constants.py')
