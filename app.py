from flask import Flask, render_template, request, jsonify, send_file
import imaplib
import os
import time
import shutil
import re
from email.header import decode_header
import threading
import logging
import email  # ✅ ADD THIS LINE
app = Flask(__name__)

# =============
# UTILS (Reuse your existing functions)
# =============

def clean_extracted_folder(folder_path):
    if os.path.exists(folder_path):
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'⚠️ Failed to delete {file_path}. Reason: {e}')

def merge_txt_files(input_folder, output_file, separator):
    files = sorted([
        f for f in os.listdir(input_folder)
        if f.endswith('.txt') and f.startswith('email_')
    ])
    if not files:
        return False
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for i, filename in enumerate(files):
            filepath = os.path.join(input_folder, filename)
            with open(filepath, 'r', encoding='utf-8', errors='replace') as infile:
                content = infile.read()
                outfile.write(content)
                if i < len(files) - 1:
                    outfile.write(f"\n{separator}\n")
    return True

def find_9digit_id_starting_with_1(text):
    if not text:
        return []
    pattern = r'1\d{8}'
    matches = re.findall(pattern, text)
    return matches

def decode_email_header(header_value):
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    decoded_str = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                decoded_str += part.decode(encoding or 'utf-8', errors='replace')
            except:
                decoded_str += part.decode('latin-1', errors='replace')
        else:
            decoded_str += part
    return decoded_str

def clean_text(text):
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except:
            text = text.decode('latin-1', errors='replace')
    if isinstance(text, str):
        text = re.sub(r'\s+', ' ', text)
    return text.strip() if text else ""

# =============
# CORE FUNCTIONS (Modified to return status + output)
# =============

def extract_emails(email_user, app_password, start_index, num_emails, folder="INBOX"):
    output_dir = "extracted_emails"
    clean_extracted_folder(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password)
        
        # Select folder
        if folder == "PROMOTIONS":
            status, _ = mail.select('"[Gmail]/Promotions"')
            if status != "OK":
                mail.select("INBOX")
        else:
            mail.select("INBOX")

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            return {"error": "Failed to search emails."}

        email_ids = messages[0].split()
        email_ids = email_ids[::-1]  # Newest first
        total_emails = len(email_ids)

        if start_index < 1 or start_index > total_emails:
            return {"error": f"Start index must be between 1 and {total_emails}."}

        start_pos = start_index - 1
        end_pos = start_pos + num_emails
        if end_pos > total_emails:
            end_pos = total_emails

        selected_ids = email_ids[start_pos:end_pos]
        saved_count = 0

        for i, e_id in enumerate(selected_ids, 1):
            try:
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    continue
                raw_email = msg_data[0][1].decode("utf-8", errors="replace")
                original_index = start_pos + i
                filename = f"{output_dir}/email_{original_index}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(raw_email)
                saved_count += 1
                time.sleep(0.1)
            except:
                continue

        mail.logout()

        # Merge
        merge_success = merge_txt_files(output_dir, "merged_emails.txt", "__SEP__")
        if merge_success:
            return {"success": f"Extracted {saved_count} emails. Check merged_emails.txt"}
        else:
            return {"error": "Merge failed."}

    except Exception as e:
        return {"error": str(e)}

import logging

def extract_ids(email_user, app_password, start_index, num_emails):
    output_file = "extracted_ids.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_password)
        mail.select("INBOX")

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            return {"error": "Failed to search emails."}

        email_ids = messages[0].split()
        email_ids = email_ids[::-1]  # Newest first
        total_emails = len(email_ids)

        if start_index < 1 or start_index > total_emails:
            return {"error": f"Start index must be between 1 and {total_emails}."}

        start_pos = start_index - 1
        end_pos = start_pos + num_emails
        if end_pos > total_emails:
            end_pos = total_emails

        selected_ids = email_ids[start_pos:end_pos]
        found_ids = set()

        for e_id in selected_ids:
            try:
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    continue
                raw_email = msg_data[0][1].decode("utf-8", errors="replace")
                msg = email.message_from_string(raw_email)

                # 🧪 DECODE FROM AND SUBJECT
                from_header = msg.get("From", "")
                subject_header = msg.get("Subject", "")

                # ✅ FULLY DECODE FROM HEADER
                from_decoded = decode_email_header(from_header)
                subject_decoded = decode_email_header(subject_header)

                # ✅ CLEAN TEXT
                from_clean = clean_text(from_decoded)
                subject_clean = clean_text(subject_decoded)

                # 🧪 DEBUG: LOG WHAT WE'RE SEARCHING
                app.logger.info(f"\n--- Email ID: {e_id.decode()} ---")
                app.logger.info(f"📩 From (cleaned): {from_clean}")
                app.logger.info(f"📌 Subject (cleaned): {subject_clean}")

                # 🔍 SEARCH FOR IDS
                ids_in_from = find_9digit_id_starting_with_1(from_clean)
                ids_in_subject = find_9digit_id_starting_with_1(subject_clean)
                all_ids = ids_in_from + ids_in_subject

                if all_ids:
                    found_ids.update(all_ids)
                    app.logger.info(f"✅ FOUND IDS: {all_ids}")
                else:
                    app.logger.info("❌ No IDs found in this email")

            except Exception as e:
                app.logger.error(f"⚠️ Error processing email {e_id.decode()}: {e}")
                continue

        mail.logout()

        with open(output_file, "w", encoding="utf-8") as f:
            for id_str in sorted(found_ids):
                f.write(id_str + "\n")

        return {"success": f"Found {len(found_ids)} IDs. Check extracted_ids.txt"}

    except Exception as e:
        return {"error": str(e)}

# =============
# FLASK ROUTES
# =============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract_inbox', methods=['POST'])
def extract_inbox():
    data = request.json
    result = extract_emails(
        data['email'],
        data['app_password'],
        int(data['start_index']),
        int(data['num_emails']),
        "INBOX"
    )
    return jsonify(result)

@app.route('/extract_promotions', methods=['POST'])
def extract_promotions():
    data = request.json
    result = extract_emails(
        data['email'],
        data['app_password'],
        int(data['start_index']),
        int(data['num_emails']),
        "PROMOTIONS"
    )
    return jsonify(result)

@app.route('/extract_ids', methods=['POST'])
def extract_ids_route():
    data = request.json
    result = extract_ids(
        data['email'],
        data['app_password'],
        int(data['start_index']),
        int(data['num_emails'])
    )
    return jsonify(result)

if __name__ == '__main__':
    # Enable debug logging
    app.logger.setLevel(logging.INFO)
    app.run(host='0.0.0.0', port=8080, debug=True)