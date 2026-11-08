# Automated Expense Management System

## Install
Open Command Prompt in this folder and run:
```bash
python -m pip install -r requirements.txt
```

## Start
```bash
python -m streamlit run app.py
```

## Reports Centre
Open **Reports Centre** and choose a report button:
- Employee-wise
- Category-wise
- Monthly
- Date-wise
- Payment-wise
- Department-wise
- Designation-wise
- Approval-wise
- Project-wise

Each selected report can be downloaded as CSV or Excel. The **Category-wise input totals** section includes every submission, with total input count, processed count, error count, and total amount per category. Download its Excel workbook for both a category summary and category transaction details. Use **Download ALL reports (multi-sheet Excel)** to export every report plus processed/error records and category-wise sheets in one workbook.

## Import data
Use **Upload Expenses** to import a CSV or Excel file. The uploaded file is previewed before import. For Payment-wise reports, include a `Payment Mode` column. If payment mode is absent, those records cannot be assigned to UPI, Cash, Card, or Bank Transfer.

## Existing database
The app continues using `data/expenses.db` and the `actual` workspace in the existing `expenses` table. Keep your existing `data` and `vouchers` folders when replacing the app file so previously entered records and attachments remain available.

## Notes
- This is a local application intended for demonstration and controlled use.
- Duplicate and missing-field checks flag records for review; they do not prove fraud.
- A production deployment should add user authentication, role permissions, backups, and an audit trail.


## Correct working import CSV
Use `working_expense_import.csv` from this package. It includes all required fields, including Payment Mode, and is formatted with ISO dates and numeric amounts. It contains 20 actual-format example rows for testing; replace these with authorised organisation records before a real deployment.

## Delete entered data
Open **Manage Data**:
- Select individual record IDs and confirm to delete selected rows.
- Or tick the confirmation box and type `DELETE ALL` to delete all expense records.
- Voucher attachments are deliberately not automatically deleted.

## Duplicate detection and approval workflow
- A duplicate is detected when Employee Name, Department, Expense Date, Amount, and Purpose all match (text matching ignores case and extra spaces; amounts are compared to two decimal places). Employee ID is also compared when supplied, but is not mandatory.
- Designation and voucher number are not used to decide whether two expense claims are duplicates.
- The first matching claim remains eligible for processing; a later matching submission is flagged as a duplicate for review.
- New manual entries and uploaded records always begin with **Pending** approval.
- The Approve button is shown only for records whose validation result is **Processed** and whose approval status is **Pending**.
- Error, duplicate, and invalid records stay **Pending** and cannot be approved from the app.
- Approvals are saved in the existing SQLite database.


## Approval management
Open **Processed & Error Records**:
- Select one or more successfully processed records from the selection list.
- **Approve Selected** approves only the selected records.
- **Waiting** changes the selected records' approval status to Waiting.
- **Pending** changes the selected records' approval status back to Pending.
- **Approve All** approves every successfully processed record at once.
- Error, duplicate, and invalid records are not included in the approval selection and remain Pending.


## Employee-wise input data downloads
In Reports Centre, use **Employee-wise input data download** to select one or more employees.
Download Excel includes a combined input-data sheet, an employee summary sheet, and a separate worksheet for each selected employee. CSV download is also available. The export includes all submitted records for the selected employees, including processed and error/duplicate records.
