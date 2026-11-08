import os, io, sqlite3, re
from datetime import date, datetime
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "data", "expenses.db")
VOUCHERS = os.path.join(ROOT, "vouchers")
os.makedirs(os.path.dirname(DB), exist_ok=True)
os.makedirs(VOUCHERS, exist_ok=True)

st.set_page_config(page_title="AUTOMATED EXPENSE MANAGEMENT SYSTEM", page_icon="💼", layout="wide")
st.markdown("""
<style>
.stApp {background:linear-gradient(135deg,#0b1020,#111d31);color:#edf2ff}
section[data-testid="stSidebar"] {background:#080e1a}
div[data-testid="stMetric"] {background:#17263b;border:1px solid #30445f;padding:14px;border-radius:14px}
div.stButton>button {border-radius:10px;font-weight:650;min-height:42px}
</style>
""", unsafe_allow_html=True)

FIELDS = ["Employee ID","Employee Name","Designation","Department","Expense Date","Category","Amount","Payment Mode","Purpose","Voucher Number","Voucher File","Project / Cost Centre","Approval Status","Approver","Submission Date","Tax / GST Amount","Location","Reimbursement Status","Remarks"]
REQUIRED = ["Employee Name","Designation","Department","Expense Date","Category","Amount","Payment Mode","Purpose"]
ALIASES = {
    "employee":"Employee Name","name":"Employee Name","employee_name":"Employee Name","employee name":"Employee Name",
    "employee id":"Employee ID","employee_id":"Employee ID","emp id":"Employee ID",
    "designation":"Designation","department":"Department","date":"Expense Date","expense_date":"Expense Date","expense date":"Expense Date",
    "expense category":"Category","category":"Category","expense amount":"Amount","amount":"Amount",
    "payment_mode":"Payment Mode","payment mode":"Payment Mode","payment method":"Payment Mode","mode":"Payment Mode",
    "description":"Purpose","purpose":"Purpose","need":"Purpose","voucher":"Voucher Number","voucher no":"Voucher Number",
    "voucher number":"Voucher Number","voucher reference":"Voucher Number","payment voucher":"Voucher Number",
    "project":"Project / Cost Centre","project/cost centre":"Project / Cost Centre","project / cost centre":"Project / Cost Centre"
}

def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS expenses(
      id INTEGER PRIMARY KEY, workspace TEXT, employee_id TEXT, employee_name TEXT,
      designation TEXT, department TEXT, expense_date TEXT, category TEXT, amount REAL,
      payment_mode TEXT, purpose TEXT, voucher_number TEXT, voucher_file TEXT,
      project TEXT, approval_status TEXT, approver TEXT, submission_date TEXT,
      tax REAL, location TEXT, reimbursement TEXT, remarks TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS limits(
      designation TEXT, category TEXT, amount REAL, UNIQUE(designation,category))""")
    c.commit()
    return c

def normalise(df):
    x = df.copy()
    x.columns = [ALIASES.get(str(c).strip().lower(), str(c).strip()) for c in x.columns]
    for col in FIELDS:
        if col not in x.columns:
            x[col] = ""
    return x[FIELDS]

def get_records():
    c = db()
    x = pd.read_sql_query("SELECT * FROM expenses WHERE workspace='actual' ORDER BY expense_date DESC, id DESC", c)
    c.close()
    if x.empty:
        return pd.DataFrame(columns=FIELDS)
    rename = {
      "employee_id":"Employee ID","employee_name":"Employee Name","designation":"Designation",
      "department":"Department","expense_date":"Expense Date","category":"Category","amount":"Amount",
      "payment_mode":"Payment Mode","purpose":"Purpose","voucher_number":"Voucher Number",
      "voucher_file":"Voucher File","project":"Project / Cost Centre","approval_status":"Approval Status",
      "approver":"Approver","submission_date":"Submission Date","tax":"Tax / GST Amount",
      "location":"Location","reimbursement":"Reimbursement Status","remarks":"Remarks"
    }
    return x.rename(columns=rename).rename(columns={"id":"Record ID"})[["Record ID"] + FIELDS]

def save_records(df):
    x = normalise(df)
    c = db()
    for _, r in x.iterrows():
        vals = [
          "actual", str(r["Employee ID"]), str(r["Employee Name"]), str(r["Designation"]),
          str(r["Department"]), str(r["Expense Date"]), str(r["Category"]),
          pd.to_numeric(r["Amount"], errors="coerce"), str(r["Payment Mode"]), str(r["Purpose"]),
          str(r["Voucher Number"]), str(r["Voucher File"]), str(r["Project / Cost Centre"]),
          "Pending", "", str(r["Submission Date"]),
          pd.to_numeric(r["Tax / GST Amount"], errors="coerce"), str(r["Location"]),
          str(r["Reimbursement Status"]), str(r["Remarks"])
        ]
        c.execute("""INSERT INTO expenses(workspace,employee_id,employee_name,designation,department,
          expense_date,category,amount,payment_mode,purpose,voucher_number,voucher_file,project,
          approval_status,approver,submission_date,tax,location,reimbursement,remarks)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
    c.commit()
    c.close()

def analyse(raw):
    record_ids = raw["Record ID"].copy() if "Record ID" in raw.columns else pd.Series([None] * len(raw), index=raw.index)
    x = normalise(raw)
    x["Record ID"] = record_ids.values
    reasons, statuses, details = [], [], []
    c = db()
    limits = pd.read_sql_query("SELECT designation,category,amount FROM limits", c)
    c.close()
    limit_map = {(str(r.designation).lower(),str(r.category).lower()):float(r.amount) for r in limits.itertuples()}
    seen = set()
    for idx, r in x.iterrows():
        issues = []
        for col in REQUIRED:
            val = str(r[col]).strip()
            if not val or val.lower() == "nan":
                issues.append("Missing " + col)
        parsed = pd.to_datetime(r["Expense Date"], errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            issues.append("Invalid expense date")
        else:
            x.at[idx, "Expense Date"] = parsed.strftime("%Y-%m-%d")
        try:
            amount = float(str(r["Amount"]).replace(",","").replace("₹","").strip())
            if amount <= 0: issues.append("Amount must be greater than zero")
            x.at[idx, "Amount"] = amount
        except Exception:
            amount = None
            issues.append("Amount is not numeric")
        if not str(r["Voucher Number"]).strip() and not str(r["Voucher File"]).strip():
            issues.append("Voucher missing")
        # Duplicate fingerprint: employee name, department, date, amount and purpose.
        # Employee ID is included when supplied, but is not mandatory.
        # Designation and voucher number do not determine whether two claims are duplicates.
        def clean_text(value):
            return " ".join(str(value).strip().casefold().split())
        if amount is not None and not pd.isna(parsed):
            key = (clean_text(r["Employee ID"]), clean_text(r["Employee Name"]),
                   clean_text(r["Department"]), parsed.strftime("%Y-%m-%d"),
                   round(amount, 2), clean_text(r["Purpose"]))
            if all(part != "" for part in (key[1], key[2], key[5])):
                if key in seen:
                    issues.append("Duplicate expense: same employee, department, date, amount and purpose")
                else:
                    seen.add(key)
        cap = limit_map.get((str(r["Designation"]).lower(),str(r["Category"]).lower()))
        if cap is not None and amount is not None and amount > cap:
            issues.append(f"Designation/category limit exceeded: ₹{cap:,.2f}")
        reasons.append("; ".join(dict.fromkeys(issues)))
        statuses.append("Error" if issues else "Processed")
        details.append("Voucher reference recorded; authenticity requires independent review.")
    x["Error Reason"] = reasons
    x["Record Status"] = statuses
    x["Approval Status"] = [
        (str(v).strip() if str(v).strip() in ("Pending", "Waiting", "Approved", "Rejected") else "Pending")
        if status == "Processed" else "Pending"
        for v, status in zip(x["Approval Status"], statuses)
    ]
    x["Voucher Check Details"] = details
    return x

def filtered_data(x):
    if x.empty: return x
    start = st.date_input("From date", value=None, key="report_from")
    end = st.date_input("To date", value=None, key="report_to")
    if start:
        x = x[pd.to_datetime(x["Expense Date"], errors="coerce").dt.date >= start]
    if end:
        x = x[pd.to_datetime(x["Expense Date"], errors="coerce").dt.date <= end]
    employees = sorted([str(v) for v in x["Employee Name"].dropna().unique() if str(v).strip()])
    chosen = st.multiselect("Employee filter", employees, default=employees, key="report_employees")
    if chosen: x = x[x["Employee Name"].astype(str).isin(chosen)]
    elif employees: x = x.iloc[0:0]
    return x

def summary_report(x, dimension):
    if x.empty: return pd.DataFrame(columns=[dimension,"Transactions","Total Amount"])
    g = x.groupby(dimension, dropna=False).agg(
        Transactions=("Amount","count"), **{"Total Amount":("Amount","sum")}
    ).reset_index()
    return g.sort_values("Total Amount", ascending=False)

def report_bytes(report):
    return report.to_csv(index=False).encode("utf-8-sig")

def workbook_bytes(reports):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as writer:
        for name, frame in reports.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    b.seek(0)
    return b.getvalue()

def current_analysis():
    raw = get_records()
    return analyse(raw) if not raw.empty else pd.DataFrame(columns=FIELDS+["Error Reason","Record Status","Voucher Check Details"])

st.sidebar.title("💼 Expense Management")
page = st.sidebar.radio("Modules", ["Dashboard","Add Expense","Upload Expenses","Processed & Error Records","Reports Centre","Employee Limits","Voucher Review","Manage Data"])
st.title("AUTOMATED EXPENSE MANAGEMENT SYSTEM")
st.caption("Employee claims • expense validation • reporting • analytics")

if page == "Dashboard":
    a = current_analysis()
    good = a[a["Record Status"]=="Processed"] if not a.empty else a
    bad = a[a["Record Status"]=="Error"] if not a.empty else a
    total = pd.to_numeric(good["Amount"],errors="coerce").sum() if not good.empty else 0
    m = st.columns(4)
    m[0].metric("Total submissions",len(a)); m[1].metric("Processed",len(good))
    m[2].metric("Needs attention",len(bad)); m[3].metric("Processed amount",f"₹{total:,.2f}")
    if a.empty: st.info("No expense records yet. Add an expense or upload an organisation CSV/Excel file.")
    else:
        l,r = st.columns(2)
        with l:
            st.subheader("Category spending")
            st.bar_chart(good.groupby("Category")["Amount"].sum())
        with r:
            st.subheader("Monthly spending")
            d = pd.to_datetime(good["Expense Date"],errors="coerce")
            st.line_chart(good.assign(Month=d.dt.to_period("M").astype(str)).groupby("Month")["Amount"].sum())
        l,r = st.columns(2)
        with l:
            st.subheader("Employee spending")
            st.bar_chart(good.groupby("Employee Name")["Amount"].sum().sort_values(ascending=False))
        with r:
            st.subheader("Payment mode")
            pm = good[good["Payment Mode"].astype(str).str.strip()!=""]
            if pm.empty: st.info("Payment mode is not present in the imported records.")
            else: st.bar_chart(pm.groupby("Payment Mode")["Amount"].sum())
        st.subheader("Recent expense records")
        st.dataframe(a,use_container_width=True,hide_index=True)

elif page == "Add Expense":
    st.subheader("Enter an employee expense")
    with st.form("expense_entry", clear_on_submit=True):
        c = st.columns(3)
        eid = c[0].text_input("Employee ID")
        name = c[1].text_input("Employee Name*")
        designation = c[2].text_input("Designation*")
        c = st.columns(3)
        department = c[0].text_input("Department*")
        exp_date = c[1].date_input("Expense Date",date.today())
        category = c[2].selectbox("Category",["Travel","Food","Accommodation","Local Conveyance","Office Supplies","Communication","Training","Medical","Client Meeting","Other"])
        c = st.columns(3)
        amount = c[0].number_input("Amount ₹",min_value=0.0,step=100.0)
        payment = c[1].selectbox("Payment Mode",["UPI","Cash","Debit Card","Credit Card","Bank Transfer","Other"])
        voucher = c[2].text_input("Voucher Number")
        purpose = st.text_input("Purpose / Description*")
        project = st.text_input("Project / Cost Centre")
        st.info("Approval status: Pending (an approver can review it after successful processing).")
        approver = ""
        tax = st.number_input("Tax / GST Amount ₹",min_value=0.0)
        location = st.text_input("Location")
        remarks = st.text_area("Remarks")
        attachment = st.file_uploader("Voucher attachment",type=["png","jpg","jpeg","pdf"])
        submit = st.form_submit_button("Save expense",use_container_width=True)
    if submit:
        filename = ""
        if attachment:
            filename = datetime.now().strftime("%Y%m%d%H%M%S_")+re.sub(r"[^A-Za-z0-9_.-]","_",attachment.name)
            with open(os.path.join(VOUCHERS,filename),"wb") as f: f.write(attachment.getbuffer())
        row = {"Employee ID":eid,"Employee Name":name,"Designation":designation,"Department":department,
               "Expense Date":exp_date,"Category":category,"Amount":amount,"Payment Mode":payment,
               "Purpose":purpose,"Voucher Number":voucher,"Voucher File":filename,
               "Project / Cost Centre":project,"Approval Status":"Pending","Approver":approver,
               "Tax / GST Amount":tax,"Location":location,"Remarks":remarks}
        save_records(pd.DataFrame([row]))
        st.success("Expense saved successfully.")

elif page == "Upload Expenses":
    st.subheader("Import employee expense records")
    uploaded = st.file_uploader("Choose CSV or Excel file",type=["csv","xlsx","xls"])
    if uploaded:
        try:
            raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
            clean = normalise(raw)
            st.write(f"{len(clean)} rows detected")
            st.dataframe(clean.head(25),use_container_width=True,hide_index=True)
            if st.button("Import records",type="primary"):
                save_records(clean)
                st.success(f"Imported {len(clean)} records.")
        except Exception as exc:
            st.error(f"Could not read this file: {exc}")
    st.caption("For payment-wise reporting, include a Payment Mode column in the uploaded file (UPI, Cash, Card, Bank Transfer, etc.).")

elif page == "Processed & Error Records":
    st.subheader("Python validation results and approval management")
    if st.button("Run validation",type="primary"):
        st.session_state["refresh_analysis"] = True
    a = current_analysis()
    good = a[a["Record Status"]=="Processed"].copy() if not a.empty else a
    bad = a[a["Record Status"]=="Error"].copy() if not a.empty else a
    m = st.columns(4)
    m[0].metric("Total",len(a)); m[1].metric("Processed",len(good))
    m[2].metric("Errors / duplicates",len(bad))
    m[3].metric("Pending approval",int((good["Approval Status"]=="Pending").sum()) if not good.empty else 0)

    st.subheader("Approval controls")
    st.caption("Select one or more successfully processed records below, then choose an action. Error, duplicate and invalid records cannot be approved.")
    if good.empty:
        st.info("There are no successfully processed records to manage.")
    else:
        choices = good[["Record ID","Employee Name","Department","Expense Date","Category","Amount","Purpose","Approval Status"]].copy()
        choices["Select Label"] = choices.apply(
            lambda r: f'#{int(r["Record ID"])} | {r["Employee Name"]} | {r["Expense Date"]} | {r["Category"]} | ₹{float(r["Amount"]):,.2f} | {r["Approval Status"]}',
            axis=1
        )
        selected_ids = st.multiselect(
            "Select the expense records you want to update",
            options=choices["Record ID"].astype(int).tolist(),
            format_func=lambda rid: choices.loc[choices["Record ID"]==rid,"Select Label"].iloc[0],
            key="approval_selected_ids"
        )
        st.write(f"Selected records: **{len(selected_ids)}**")

        def set_approval(ids, status):
            if not ids:
                return 0
            c = db()
            placeholders = ",".join(["?"] * len(ids))
            c.execute(
                f"""UPDATE expenses SET approval_status=?, approver=?
                    WHERE workspace='actual' AND id IN ({placeholders})""",
                [status, "Approver", *[int(v) for v in ids]]
            )
            changed = c.total_changes
            c.commit()
            c.close()
            return changed

        col1,col2,col3,col4 = st.columns(4)
        with col1:
            if st.button("Approve Selected", type="primary", use_container_width=True, disabled=not selected_ids):
                changed = set_approval(selected_ids, "Approved")
                st.success(f"Approved {changed} selected record(s).")
                st.rerun()
        with col2:
            if st.button("Waiting", use_container_width=True, disabled=not selected_ids):
                changed = set_approval(selected_ids, "Waiting")
                st.success(f"Changed {changed} selected record(s) to Waiting.")
                st.rerun()
        with col3:
            if st.button("Pending", use_container_width=True, disabled=not selected_ids):
                changed = set_approval(selected_ids, "Pending")
                st.success(f"Changed {changed} selected record(s) to Pending.")
                st.rerun()
        with col4:
            all_ids = good["Record ID"].dropna().astype(int).tolist()
            if st.button("Approve All", type="primary", use_container_width=True, disabled=not all_ids):
                changed = set_approval(all_ids, "Approved")
                st.success(f"Approved all {changed} successfully processed record(s).")
                st.rerun()

        st.markdown("#### Successfully processed records")
        st.dataframe(good.drop(columns=["Select Label"], errors="ignore"),use_container_width=True,hide_index=True)
        st.download_button("Download processed CSV",report_bytes(good.drop(columns=["Record ID"], errors="ignore")),"processed_expenses.csv","text/csv")

    st.subheader("Error, duplicate and invalid records")
    st.dataframe(bad.drop(columns=["Record ID"], errors="ignore"),use_container_width=True,hide_index=True)
    st.download_button("Download error CSV",report_bytes(bad.drop(columns=["Record ID"], errors="ignore")),"expense_errors.csv","text/csv")

elif page == "Reports Centre":
    st.subheader("Reports Centre")
    a = current_analysis()
    if a.empty:
        st.info("No expense records are available. Add or upload records to generate reports.")
    else:
        valid = a[a["Record Status"]=="Processed"].copy()
        valid["Expense Date"] = pd.to_datetime(valid["Expense Date"],errors="coerce")
        valid["Month"] = valid["Expense Date"].dt.to_period("M").astype(str)
        valid["Expense Date"] = valid["Expense Date"].dt.strftime("%Y-%m-%d")
        dimensions = {
          "Employee-wise":"Employee Name",
          "Category-wise":"Category",
          "Monthly":"Month",
          "Date-wise":"Expense Date",
          "Payment-wise":"Payment Mode",
          "Department-wise":"Department",
          "Designation-wise":"Designation",
          "Approval-wise":"Approval Status",
          "Project-wise":"Project / Cost Centre"
        }
        if "selected_report" not in st.session_state: st.session_state.selected_report = "Employee-wise"
        names = list(dimensions.keys())
        cols = st.columns(3)
        for i, name in enumerate(names):
            with cols[i%3]:
                if st.button(name, key="report_"+name, use_container_width=True,
                             type="primary" if st.session_state.selected_report==name else "secondary"):
                    st.session_state.selected_report = name
        selected = st.session_state.selected_report
        st.markdown(f"### {selected} report")
        scoped = filtered_data(valid.copy())
        dim = dimensions[selected]
        if selected == "Payment-wise":
            scoped = scoped[scoped[dim].astype(str).str.strip()!=""]
        if selected == "Date-wise":
            report = scoped.sort_values("Expense Date")
        else:
            report = summary_report(scoped,dim)
        st.dataframe(report,use_container_width=True,hide_index=True)
        safe_name = selected.lower().replace("-","_").replace(" ","_")
        st.download_button(f"Download {selected} CSV",report_bytes(report),f"{safe_name}_report.csv","text/csv",use_container_width=True)
        st.download_button(f"Download {selected} Excel",workbook_bytes({selected:report}),f"{safe_name}_report.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        all_records = a.copy()
        all_records["Amount"] = pd.to_numeric(all_records["Amount"], errors="coerce")
        category_summary = all_records.groupby("Category", dropna=False).agg(
            **{"Total Inputs":("Record ID","count"),
               "Processed Inputs":("Record Status",lambda v: int((v=="Processed").sum())),
               "Error Inputs":("Record Status",lambda v: int((v=="Error").sum())),
               "Total Amount":("Amount","sum")}
        ).reset_index().sort_values("Total Amount", ascending=False)
        category_details = all_records.sort_values(["Category","Expense Date"])
        st.markdown("### Category-wise input totals")
        st.caption("Includes all submitted records, with processed and error counts shown separately.")
        st.dataframe(category_summary, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Category-wise Inputs Excel",
            workbook_bytes({"Category Summary":category_summary, "Category Transactions":category_details}),
            "category_wise_expense_inputs.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary", use_container_width=True
        )

        st.markdown("### Employee-wise input data download")
        st.caption("Choose one or more employees to download their submitted expense inputs, including processed, duplicate and error records.")
        employee_options = sorted(
            [str(v) for v in a["Employee Name"].dropna().unique() if str(v).strip()]
        )
        selected_employees = st.multiselect(
            "Select employee(s)",
            employee_options,
            default=employee_options,
            key="employee_input_download_selection"
        )
        employee_data = a[a["Employee Name"].astype(str).isin(selected_employees)].copy()
        if selected_employees and not employee_data.empty:
            employee_data = employee_data.sort_values(["Employee Name", "Expense Date"], na_position="last")
            employee_data["Amount"] = pd.to_numeric(employee_data["Amount"], errors="coerce")
            employee_summary = employee_data.groupby(
                "Employee Name", dropna=False
            ).agg(
                **{
                    "Total Inputs": ("Record ID", "count"),
                    "Processed Inputs": ("Record Status", lambda v: int((v == "Processed").sum())),
                    "Error Inputs": ("Record Status", lambda v: int((v == "Error").sum())),
                    "Total Amount": ("Amount", "sum")
                }
            ).reset_index()
            employee_sheets = {
                "Selected Employee Inputs": employee_data,
                "Employee Summary": employee_summary
            }
            # Add a separate worksheet for each employee for convenient individual review.
            used_sheet_names = set(employee_sheets)
            for employee_name in selected_employees:
                safe_sheet = re.sub(r"[\\\\/*?:\\[\\]]", "_", employee_name).strip() or "Employee"
                safe_sheet = safe_sheet[:31]
                base_sheet = safe_sheet
                suffix = 2
                while safe_sheet in used_sheet_names:
                    tail = f"_{suffix}"
                    safe_sheet = base_sheet[:31-len(tail)] + tail
                    suffix += 1
                used_sheet_names.add(safe_sheet)
                employee_sheets[safe_sheet] = employee_data[
                    employee_data["Employee Name"].astype(str) == employee_name
                ].copy()
            st.write(f"Selected records: **{len(employee_data)}** across **{len(selected_employees)}** employee(s).")
            st.dataframe(employee_summary, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Selected Employee Input Data (Excel)",
                workbook_bytes(employee_sheets),
                "employee_wise_input_data.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            st.download_button(
                "Download Selected Employee Input Data (CSV)",
                report_bytes(employee_data),
                "employee_wise_input_data.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.info("Select at least one employee to enable the employee-wise download.")

        all_reports = {}
        for label, field in dimensions.items():
            subset = valid.copy()
            if label == "Payment-wise": subset = subset[subset[field].astype(str).str.strip()!=""]
            all_reports[label] = subset.sort_values("Expense Date") if label=="Date-wise" else summary_report(subset,field)
        all_reports["Processed Records"] = valid
        all_reports["Error Records"] = a[a["Record Status"]=="Error"]
        all_reports["Category Input Summary"] = category_summary
        all_reports["Category Transactions"] = category_details
        st.download_button("Download ALL reports (multi-sheet Excel)",workbook_bytes(all_reports),
                           "employee_expense_all_reports.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary",use_container_width=True)

elif page == "Employee Limits":
    st.subheader("Designation and category spending limits")
    with st.form("limits"):
        designation = st.text_input("Designation")
        category = st.selectbox("Category",["Travel","Food","Accommodation","Local Conveyance","Office Supplies","Communication","Training","Medical","Client Meeting","Other"])
        amount = st.number_input("Maximum per claim ₹",min_value=0.0,step=500.0)
        save = st.form_submit_button("Save limit")
    if save and designation.strip():
        c = db()
        c.execute("INSERT INTO limits VALUES(?,?,?) ON CONFLICT(designation,category) DO UPDATE SET amount=excluded.amount",
                  (designation.strip(),category,amount))
        c.commit(); c.close(); st.success("Limit saved.")
    c = db()
    limits = pd.read_sql_query("SELECT designation AS Designation,category AS Category,amount AS Limit_Rs FROM limits",c)
    c.close()
    st.dataframe(limits,use_container_width=True,hide_index=True)

elif page == "Voucher Review":
    st.warning("Voucher references and attachments can be reviewed, but these checks do not prove authenticity.")
    a = current_analysis()
    if a.empty: st.info("No expense records.")
    else:
        st.dataframe(a[["Employee ID","Employee Name","Expense Date","Amount","Voucher Number","Voucher File","Voucher Check Details"]],
                     use_container_width=True,hide_index=True)
    st.caption("Image OCR requires Tesseract OCR to be installed separately. PDF vouchers require manual review.")


elif page == "Manage Data":
    st.subheader("Manage entered expense data")
    st.warning("Deleting records is permanent. Download a backup before deleting if you may need the data later.")
    c = db()
    stored = pd.read_sql_query(
        """SELECT id AS Record_ID, employee_id AS Employee_ID, employee_name AS Employee_Name,
        expense_date AS Expense_Date, category AS Category, amount AS Amount,
        payment_mode AS Payment_Mode, purpose AS Purpose
        FROM expenses WHERE workspace='actual' ORDER BY id DESC""", c)
    c.close()

    if stored.empty:
        st.info("There are no expense records to delete.")
    else:
        st.write(f"Current records: **{len(stored)}**")
        st.dataframe(stored, use_container_width=True, hide_index=True)

        st.markdown("#### Delete selected records")
        ids = st.multiselect(
            "Select record IDs to delete",
            options=stored["Record_ID"].astype(int).tolist(),
            format_func=lambda v: f"Record {v} — " + str(stored.loc[stored["Record_ID"] == v, "Employee_Name"].iloc[0]) +
                                  " — " + str(stored.loc[stored["Record_ID"] == v, "Expense_Date"].iloc[0])
        )
        confirm_selected = st.checkbox("I confirm that I want to permanently delete the selected records.")
        if st.button("Delete selected records", type="secondary", disabled=(not ids or not confirm_selected)):
            c = db()
            placeholders = ",".join(["?"] * len(ids))
            c.execute(f"DELETE FROM expenses WHERE workspace='actual' AND id IN ({placeholders})", ids)
            deleted = c.total_changes
            c.commit()
            c.close()
            st.success(f"Deleted {deleted} record(s).")
            st.rerun()

        st.divider()
        st.markdown("#### Delete all entered expense records")
        confirm_all = st.checkbox("I understand this will permanently delete ALL expense records in this application.")
        typed = st.text_input('Type DELETE ALL to confirm')
        if st.button("Delete ALL expense records", type="primary", disabled=not (confirm_all and typed == "DELETE ALL")):
            c = db()
            c.execute("DELETE FROM expenses WHERE workspace='actual'")
            deleted = c.total_changes
            c.commit()
            c.close()
            st.success(f"Deleted all {deleted} expense record(s).")
            st.rerun()
        st.caption("Deleting expense records does not delete voucher files from the vouchers folder. Remove those files separately only if you are certain they are no longer required.")
