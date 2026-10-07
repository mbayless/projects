"""Turn each supported input into plain text (with a little structure kept) so the detectors can scan it.

Supported: .json, .txt/.md/.log/.csv/.tsv, .xlsx/.xls, .docx, and http(s) links.
Every extractor returns a list of (segment_label, text) pairs so findings can point back to a cell,
a field path or a page section.
"""
import io, json, re


def from_text(data: bytes, name="text"):
    return [(name, data.decode("utf-8", "replace"))]


def from_json(data: bytes, name="json"):
    """Walk the JSON and emit one segment per leaf, labelled by its path, so a finding names its field."""
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return from_text(data, name)
    out = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}" if path else str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
        else:
            if v is not None and str(v).strip():
                out.append((f"{name}:{path}", str(v)))
    walk(obj, "")
    return out or from_text(data, name)


def from_csv(data: bytes, name="table"):
    import csv
    text = data.decode("utf-8", "replace")
    dialect = "excel-tab" if "\t" in text[:2000] and text[:2000].count("\t") > text[:2000].count(",") else "excel"
    rows = list(csv.reader(io.StringIO(text), dialect=dialect))
    if not rows:
        return []
    header = rows[0]
    out = []
    for r, row in enumerate(rows[1:], start=2):
        for c, cell in enumerate(row):
            if cell.strip():
                col = header[c] if c < len(header) else f"col{c + 1}"
                out.append((f"{name}!{col} (row {r})", cell))
    return out


def from_xlsx(data: bytes, name="workbook"):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            header = [str(c) if c is not None else "" for c in next(rows)]
        except StopIteration:
            continue
        for r, row in enumerate(rows, start=2):
            for c, cell in enumerate(row):
                if cell is not None and str(cell).strip():
                    col = header[c] if c < len(header) and header[c] else f"col{c + 1}"
                    out.append((f"{ws.title}!{col} (row {r})", str(cell)))
    wb.close()
    return out


def from_docx(data: bytes, name="document"):
    import docx
    doc = docx.Document(io.BytesIO(data))
    out = []
    for i, p in enumerate(doc.paragraphs, start=1):
        if p.text.strip():
            out.append((f"{name} ¶{i}", p.text))
    for t, table in enumerate(doc.tables, start=1):
        for r, row in enumerate(table.rows, start=1):
            for c, cell in enumerate(row.cells, start=1):
                if cell.text.strip():
                    out.append((f"{name} table{t} r{r}c{c}", cell.text))
    return out


def from_url(url, timeout=15):
    """Fetch a link and return its readable text. This is the only extractor that uses the network,
    and only for a URL the user explicitly provides."""
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, headers={"User-Agent": "LMpower-PHI-Scanner/1.0"}, timeout=timeout)
    ctype = r.headers.get("content-type", "")
    label = f"url:{url}"
    if "application/json" in ctype:
        return from_json(r.content, label)
    if "html" in ctype or r.text.lstrip()[:1] == "<":
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
        return [(label, text)]
    return [(label, r.text)]


EXT_MAP = {
    ".json": from_json, ".txt": from_text, ".md": from_text, ".log": from_text,
    ".csv": from_csv, ".tsv": from_csv, ".xlsx": from_xlsx, ".xlsm": from_xlsx, ".xls": from_xlsx,
    ".docx": from_docx,
}


def extract(filename, data: bytes):
    """Pick an extractor by file extension and return (label, text) segments."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    fn = EXT_MAP.get(ext, from_text)
    try:
        return fn(data, filename)
    except Exception as e:
        return [(f"{filename} (could not parse: {type(e).__name__})", data.decode("utf-8", "replace")[:100000])]
