"""Give native bar and line charts exported by the PPTD writer an Edit Data workbook."""
from io import BytesIO
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.parts.chart import ChartPart
from xlsxwriter import Workbook
from xlsxwriter.utility import xl_col_to_name


def bind_range(literal, column, length):
    """Keep the writer's exact cache, including point indices and number formatting."""
    numeric = literal.tag == qn("c:numLit")
    kind = "num" if numeric else "str"
    parent = literal.getparent()
    ref = etree.Element(qn(f"c:{kind}Ref"))
    parent.replace(literal, ref)
    letter = xl_col_to_name(column, col_abs=True)
    etree.SubElement(ref, qn("c:f")).text = f"ChartData!{letter}$2:{letter}${length + 1}"
    literal.tag = qn(f"c:{kind}Cache")
    ref.append(literal)


def write_points(sheet, column, literal):
    numeric = literal.tag == qn("c:numLit")
    for point in literal.findall(qn("c:pt")):
        value = point.findtext(qn("c:v"))
        if value in (None, ""):
            continue
        row = int(point.get("idx")) + 1
        if numeric:
            sheet.write_number(row, column, float(value))
        else:
            sheet.write_string(row, column, value)


def attach_workbook(part):
    root = part.chart._chartSpace
    if root.find(qn("c:externalData")) is not None:
        return False
    series = root.xpath("./c:chart/c:plotArea/*/c:ser")
    if not series or any(s.getparent().tag not in {qn("c:lineChart"), qn("c:barChart")} for s in series):
        return False
    columns = {}
    stream = BytesIO()
    with Workbook(stream, {"in_memory": True}) as book:
        sheet = book.add_worksheet("ChartData")
        next_column = 0
        for item in series:
            cat, = item.xpath("./c:cat/c:strLit | ./c:cat/c:numLit")
            val, = item.xpath("./c:val/c:numLit")
            # Series sharing the same categories use one worksheet column.
            key = etree.tostring(cat, method="c14n")
            if key not in columns:
                columns[key] = next_column
                sheet.write_string(0, next_column, "Category")
                write_points(sheet, next_column, cat)
                next_column += 1
            size = int(cat.find(qn("c:ptCount")).get("val"))
            bind_range(cat, columns[key], max(1, size))
            write_points(sheet, next_column, val)
            size = int(val.find(qn("c:ptCount")).get("val"))
            bind_range(val, next_column, max(1, size))

            name = item.find("c:tx/c:v", namespaces=item.nsmap)
            if name is not None:
                sheet.write_string(0, next_column, name.text or "")
                ref = etree.Element(qn("c:strRef"))
                name.getparent().replace(name, ref)
                etree.SubElement(ref, qn("c:f")).text = f"ChartData!{xl_col_to_name(next_column, True)}$1"
                cache = etree.SubElement(ref, qn("c:strCache"))
                etree.SubElement(cache, qn("c:ptCount"), val="1")
                etree.SubElement(cache, qn("c:pt"), idx="0").append(name)
            next_column += 1
    part.chart_workbook.update_from_xlsx_blob(stream.getvalue())
    return True


def embed_chart_workbooks(pptx_path: Path) -> int:
    deck = Presentation(pptx_path)
    charts = [part for part in deck.part.package.iter_parts() if isinstance(part, ChartPart)]
    count = sum(attach_workbook(part) for part in charts)
    if count:
        # The caller supplies its private pending PPTX. It publishes the result
        # only after the complete package passes its normal export checks.
        deck.save(pptx_path)
    return count
