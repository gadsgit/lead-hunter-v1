"""
log_update.py — Update Log Utility
Format: One row per file. Each update appends a new date column.
Usage: python log_update.py "filename.py" "What changed"
"""
import sys
import os
import datetime
import pandas as pd

LOG_EXCEL = r"E:\Lead Hunter\update_log.xlsx"

def append_log(file_updated: str, details: str):
    now_ist = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")
    entry = f"{now_ist} — {details}"

    # Load existing log or start fresh
    if os.path.isfile(LOG_EXCEL):
        df = pd.read_excel(LOG_EXCEL)
    else:
        df = pd.DataFrame(columns=["File Name"])

    # Find if file already has a row
    if file_updated in df["File Name"].values:
        row_idx = df.index[df["File Name"] == file_updated][0]
        # Count existing update columns for this file
        update_cols = [c for c in df.columns if c.startswith("Update ")]
        next_num = 1
        for col in update_cols:
            if pd.isna(df.at[row_idx, col]) or df.at[row_idx, col] == "":
                # Fill first empty slot
                df.at[row_idx, col] = entry
                next_num = None
                break
            next_num = int(col.split(" ")[1]) + 1
        if next_num:
            # All existing slots filled — create a new column
            new_col = f"Update {next_num}"
            df[new_col] = ""
            df.at[row_idx, new_col] = entry
    else:
        # New file — add a row
        new_row = {"File Name": file_updated, "Update 1": entry}
        if "Update 1" not in df.columns:
            df["Update 1"] = ""
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_excel(LOG_EXCEL, index=False)
    print(f"[LOG] {entry} → {file_updated}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python log_update.py <filename> <description>")
        sys.exit(1)
    append_log(sys.argv[1], sys.argv[2])
