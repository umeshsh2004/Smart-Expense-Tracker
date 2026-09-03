"""Export expenses to Excel and PDF."""

import io


def build_excel(rows) -> io.BytesIO:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["Date", "Category", "Description", "Amount"])
    for row in rows:
        ws.append([row["date"], row["category"], row["description"], float(row["amount"])])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_pdf(rows) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Expense Report", ln=1)
    pdf.set_font("Helvetica", size=9)
    pdf.ln(4)
    for row in rows:
        line = f"{row['date']}  |  {row['category']}  |  {row['description']}  |  {float(row['amount']):.2f}"
        pdf.multi_cell(0, 6, line)
    # fpdf2 returns str or bytes depending on version
    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
