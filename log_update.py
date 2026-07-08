"""
log_update.py — Update Log Utility
Usage: python log_update.py "filename.py" "What changed"
Called automatically after every code change to keep update_log.xlsx and update_log.csv current.
"""
import sys
import os
import datetime
import pandas as pd

LOG_EXCEL = r"E:\Lead Hunter\update_log.xlsx"
LOG_CSV   = r"E:\Lead Hunter\update_log.csv"

def append_log(file_updated: str, details: str):
    now_ist = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")

    new_row = pd.DataFrame([{
        "Date & Time (IST)": now_ist,
        "File Updated":       file_updated,
        "Update Details":     details
    }])

    # --- CSV ---
    file_exists = os.path.isfile(LOG_CSV)
    new_row.to_csv(LOG_CSV, mode="a", header=not file_exists, index=False)

    # --- Excel ---
    if os.path.isfile(LOG_EXCEL):
        df_existing = pd.read_excel(LOG_EXCEL)
        df_combined = pd.concat([df_existing, new_row], ignore_index=True)
    else:
        df_combined = new_row

    df_combined.to_excel(LOG_EXCEL, index=False)
    print(f"[LOG] {now_ist} | {file_updated} | {details}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python log_update.py <filename> <description>")
        sys.exit(1)
    append_log(sys.argv[1], sys.argv[2])
