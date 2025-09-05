import os
import time
import subprocess
from google.oauth2 import service_account
from googleapiclient.discovery import build

# CONFIG
SPREADSHEET_ID = '1f7bRhLfjF0zwvUICW8JNHOQeZsheiCY_C9NwBMGqvX0'
SHEET_NAME = 'Kids'
RANGE = f'{SHEET_NAME}!A2:H'  # Row 1 is header, read from row 2 down

# Auth
creds = service_account.Credentials.from_service_account_file(
    'service_account.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

def check_new_entries():
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE).execute()
    rows = result.get('values', [])

    updates = []

    for i, row in enumerate(rows):
        row_index = i + 2  # account for header
        notified = row[7] if len(row) >= 8 else ''
        if notified.strip().lower() == 'yes':
            continue

        preview = row[2] if len(row) > 2 else '(No Subject)'
        link = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0&range=A{row_index}'

        # macOS popup
        script = f'''
        display dialog "📝 New Entry:\n\n{preview}" buttons ["Mark Complete", "Open Sheet"] default button "Open Sheet" with title "New Row in Kids Sheet" with icon note
        '''
        try:
            result = subprocess.check_output(['osascript', '-e', script]).decode()

            if "Open Sheet" in result:
                subprocess.call(["open", link])
            elif "Mark Complete" in result:
                print("✔️ Marked complete — local only for now.")

            # Mark as notified in column H
            updates.append({
                'range': f'{SHEET_NAME}!H{row_index}',
                'values': [['Yes']]
            })

        except subprocess.CalledProcessError:
            print("Popup dismissed or error showing dialog.")

    if updates:
        sheet.values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
            'valueInputOption': 'RAW',
            'data': updates
        }).execute()

# Loop forever
if __name__ == "__main__":
    print("🔁 Starting Google Sheet polling loop...")
    while True:
        try:
            check_new_entries()
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(30)