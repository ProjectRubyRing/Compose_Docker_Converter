"""標準ライブラリだけで .xlsx (Excel ブック) を書き出す小さなライター。

RHEL 9 の python3 には openpyxl などが入っていないことが多いため、
Office Open XML (zip + XML) を直接作ります。対応している機能:

* 複数シート / シート見出しの色
* フォント (Meiryo UI)・太字・色、塗りつぶし、罫線、折り返し、縦横の配置
* 列の幅・行の高さ・セルの結合・ウィンドウ枠の固定・オートフィルター
* シート内リンク (ハイパーリンク)・印刷設定 (横向き / 幅に合わせる / 見出し行の繰り返し)
"""

import datetime
import re
import zipfile
from xml.sax.saxutils import escape

__all__ = ["Workbook"]

_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _col_letter(col):
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def cell_ref(row, col):
    return "%s%d" % (_col_letter(col), row)


def _text(value):
    return escape(_INVALID_XML.sub("", value), {'"': "&quot;"})


class Sheet:
    def __init__(self, workbook, name, tab_color=None):
        self.wb = workbook
        self.name = name
        self.tab_color = tab_color
        self.cells = {}
        self.col_widths = {}
        self.row_heights = {}
        self.merges = []
        self.freeze = None
        self.autofilter = None
        self.hyperlinks = []
        self.landscape = True
        self.fit_width = True
        self.repeat_rows = None
        self.zoom = 100
        self.show_grid = False
        self.max_row = 0
        self.max_col = 0

    def set(self, row, col, value, style=0):
        self.cells[(row, col)] = (value, style)
        self.max_row = max(self.max_row, row)
        self.max_col = max(self.max_col, col)

    def merge(self, row1, col1, row2, col2):
        if (row1, col1) != (row2, col2):
            self.merges.append((row1, col1, row2, col2))
        self.max_row = max(self.max_row, row2)
        self.max_col = max(self.max_col, col2)

    def link(self, row, col, location, display=None):
        self.hyperlinks.append((cell_ref(row, col), location, display))

    def xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
        pr = []
        if self.tab_color:
            pr.append('<tabColor rgb="FF%s"/>' % self.tab_color)
        if self.fit_width:
            pr.append('<pageSetUpPr fitToPage="1"/>')
        out.append("<sheetPr>%s</sheetPr>" % "".join(pr))
        last = cell_ref(max(self.max_row, 1), max(self.max_col, 1))
        out.append('<dimension ref="A1:%s"/>' % last)
        view = '<sheetView workbookViewId="0" zoomScale="%d"%s%s>' % (
            self.zoom, "" if self.show_grid else ' showGridLines="0"', ' tabSelected="1"' if self.wb.sheets[0] is self else "")
        if self.freeze:
            frow, fcol = self.freeze
            attrs = []
            if fcol > 1:
                attrs.append('xSplit="%d"' % (fcol - 1))
            if frow > 1:
                attrs.append('ySplit="%d"' % (frow - 1))
            pane = "bottomRight" if (frow > 1 and fcol > 1) else ("bottomLeft" if frow > 1 else "topRight")
            view += '<pane %s topLeftCell="%s" activePane="%s" state="frozen"/>' % (" ".join(attrs), cell_ref(frow, fcol), pane)
            view += '<selection pane="%s" activeCell="%s" sqref="%s"/>' % (pane, cell_ref(frow, fcol), cell_ref(frow, fcol))
        view += "</sheetView>"
        out.append("<sheetViews>%s</sheetViews>" % view)
        out.append('<sheetFormatPr defaultRowHeight="%s"/>' % self.wb.default_row_height)
        if self.col_widths:
            cols = []
            for col in sorted(self.col_widths):
                cols.append('<col min="%d" max="%d" width="%.2f" customWidth="1"/>' % (col, col, self.col_widths[col]))
            out.append("<cols>%s</cols>" % "".join(cols))
        out.append("<sheetData>")
        rows = {}
        for (row, col), item in self.cells.items():
            rows.setdefault(row, {})[col] = item
        for row in sorted(set(rows) | set(self.row_heights)):
            attrs = 'r="%d"' % row
            if row in self.row_heights:
                attrs += ' ht="%.2f" customHeight="1"' % self.row_heights[row]
            cells = []
            for col in sorted(rows.get(row, {})):
                value, style = rows[row][col]
                ref = cell_ref(row, col)
                s_attr = ' s="%d"' % style if style else ""
                if value is None or value == "":
                    cells.append('<c r="%s"%s/>' % (ref, s_attr))
                elif isinstance(value, bool):
                    cells.append('<c r="%s"%s t="b"><v>%d</v></c>' % (ref, s_attr, 1 if value else 0))
                elif isinstance(value, (int, float)):
                    cells.append('<c r="%s"%s><v>%s</v></c>' % (ref, s_attr, repr(value)))
                else:
                    idx = self.wb.shared(str(value))
                    cells.append('<c r="%s"%s t="s"><v>%d</v></c>' % (ref, s_attr, idx))
            out.append("<row %s>%s</row>" % (attrs, "".join(cells)))
        out.append("</sheetData>")
        if self.autofilter:
            out.append('<autoFilter ref="%s"/>' % self.autofilter)
        if self.merges:
            out.append('<mergeCells count="%d">' % len(self.merges))
            for r1, c1, r2, c2 in self.merges:
                out.append('<mergeCell ref="%s:%s"/>' % (cell_ref(r1, c1), cell_ref(r2, c2)))
            out.append("</mergeCells>")
        if self.hyperlinks:
            out.append("<hyperlinks>")
            for ref, location, display in self.hyperlinks:
                out.append('<hyperlink ref="%s" location="%s" display="%s"/>' % (ref, _text(location), _text(display or location)))
            out.append("</hyperlinks>")
        out.append('<printOptions horizontalCentered="1"/>')
        out.append('<pageMargins left="0.4" right="0.4" top="0.55" bottom="0.55" header="0.3" footer="0.3"/>')
        out.append('<pageSetup paperSize="9" orientation="%s"%s/>' % (
            "landscape" if self.landscape else "portrait", ' fitToWidth="1" fitToHeight="0"' if self.fit_width else ""))
        out.append('<headerFooter><oddFooter>&amp;L&amp;"Meiryo UI,標準"&amp;8&amp;A&amp;R&amp;"Meiryo UI,標準"&amp;8&amp;P / &amp;N</oddFooter></headerFooter>')
        out.append("</worksheet>")
        return "".join(out)


class Workbook:
    def __init__(self, font_name="Meiryo UI", font_size=10, default_row_height=16.5):
        self.font_name = font_name
        self.font_size = font_size
        self.default_row_height = default_row_height
        self.sheets = []
        self._strings = {}
        self._string_list = []
        self._fonts = [(font_size, False, False, "000000", False)]
        self._fills = ["none", "gray125"]
        self._borders = [None]
        self._xfs = [(0, 0, 0, None)]
        self._xf_index = {self._xfs[0]: 0}
        self.title = ""
        self.creator = ""

    def add_sheet(self, name, tab_color=None):
        name = re.sub(r"[\[\]:*?/\\]", "_", name)[:31]
        sheet = Sheet(self, name, tab_color)
        self.sheets.append(sheet)
        return sheet

    def shared(self, text):
        if text not in self._strings:
            self._strings[text] = len(self._string_list)
            self._string_list.append(text)
        return self._strings[text]

    def style(self, size=None, bold=False, italic=False, color="000000", underline=False, fill=None,
              border=None, halign=None, valign="top", wrap=True, indent=0):
        """書式を登録して番号を返す。border は None / "thin" / "medium" / ("thin", "BFBFBF")。"""
        font = (size or self.font_size, bool(bold), bool(italic), color.upper(), bool(underline))
        if font not in self._fonts:
            self._fonts.append(font)
        font_id = self._fonts.index(font)
        fill_id = 0
        if fill:
            key = fill.upper()
            if key not in self._fills:
                self._fills.append(key)
            fill_id = self._fills.index(key)
        border_id = 0
        if border:
            if isinstance(border, str):
                border = (border, "A6A6A6")
            if border not in self._borders:
                self._borders.append(border)
            border_id = self._borders.index(border)
        align = (halign, valign, bool(wrap), int(indent))
        key = (font_id, fill_id, border_id, align)
        if key not in self._xf_index:
            self._xf_index[key] = len(self._xfs)
            self._xfs.append(key)
        return self._xf_index[key]

    # ------------------------------------------------------------------
    def _styles_xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        out.append('<fonts count="%d">' % len(self._fonts))
        for size, bold, italic, color, underline in self._fonts:
            out.append("<font>%s%s%s<sz val=\"%s\"/><color rgb=\"FF%s\"/><name val=\"%s\"/><family val=\"3\"/><charset val=\"128\"/></font>" % (
                "<b/>" if bold else "", "<i/>" if italic else "", "<u/>" if underline else "", size, color, _text(self.font_name)))
        out.append("</fonts>")
        out.append('<fills count="%d">' % len(self._fills))
        for fill in self._fills:
            if fill in ("none", "gray125"):
                out.append('<fill><patternFill patternType="%s"/></fill>' % fill)
            else:
                out.append('<fill><patternFill patternType="solid"><fgColor rgb="FF%s"/><bgColor indexed="64"/></patternFill></fill>' % fill)
        out.append("</fills>")
        out.append('<borders count="%d">' % len(self._borders))
        for border in self._borders:
            if border is None:
                out.append("<border><left/><right/><top/><bottom/><diagonal/></border>")
            else:
                style, color = border
                side = '<%%s style="%s"><color rgb="FF%s"/></%%s>' % (style, color)
                out.append("<border>%s%s%s%s<diagonal/></border>" % (
                    side % ("left", "left"), side % ("right", "right"), side % ("top", "top"), side % ("bottom", "bottom")))
        out.append("</borders>")
        out.append('<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>')
        out.append('<cellXfs count="%d">' % len(self._xfs))
        for font_id, fill_id, border_id, align in self._xfs:
            attrs = 'numFmtId="0" fontId="%d" fillId="%d" borderId="%d" xfId="0"' % (font_id, fill_id, border_id)
            if font_id:
                attrs += ' applyFont="1"'
            if fill_id:
                attrs += ' applyFill="1"'
            if border_id:
                attrs += ' applyBorder="1"'
            if align is None:
                out.append("<xf %s/>" % attrs)
                continue
            halign, valign, wrap, indent = align
            a = []
            if halign:
                a.append('horizontal="%s"' % halign)
            if valign:
                a.append('vertical="%s"' % valign)
            if wrap:
                a.append('wrapText="1"')
            if indent:
                a.append('indent="%d"' % indent)
            out.append('<xf %s applyAlignment="1"><alignment %s/></xf>' % (attrs, " ".join(a)))
        out.append("</cellXfs>")
        out.append('<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>')
        out.append('<dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>')
        out.append("</styleSheet>")
        return "".join(out)

    def _shared_xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="%d" uniqueCount="%d">' % (
                   len(self._string_list), len(self._string_list))]
        for text in self._string_list:
            space = ' xml:space="preserve"' if (text[:1].isspace() or text[-1:].isspace() or "\n" in text) else ""
            out.append("<si><t%s>%s</t></si>" % (space, _text(text)))
        out.append("</sst>")
        return "".join(out)

    def _workbook_xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
               '<workbookPr defaultThemeVersion="164011"/>'
               '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="15600" tabRatio="800"/></bookViews>'
               "<sheets>"]
        for idx, sheet in enumerate(self.sheets):
            out.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_text(sheet.name), idx + 1, idx + 1))
        out.append("</sheets>")
        names = []
        for idx, sheet in enumerate(self.sheets):
            quoted = "'%s'" % sheet.name.replace("'", "''")
            if sheet.autofilter:
                start, end = sheet.autofilter.split(":")
                names.append('<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">%s!%s:%s</definedName>' % (
                    idx, _text(quoted), _abs_ref(start), _abs_ref(end)))
            if sheet.repeat_rows:
                r1, r2 = sheet.repeat_rows
                names.append('<definedName name="_xlnm.Print_Titles" localSheetId="%d">%s!$%d:$%d</definedName>' % (
                    idx, _text(quoted), r1, r2))
        if names:
            out.append("<definedNames>%s</definedNames>" % "".join(names))
        out.append('<calcPr calcId="191029"/></workbook>')
        return "".join(out)

    def save(self, path):
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
        sheets_xml = [sheet.xml() for sheet in self.sheets]
        content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
        for idx in range(len(self.sheets)):
            content_types.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (idx + 1))
        content_types.append('<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                             '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                             '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                             "</Types>")
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                "</Relationships>")
        wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for idx in range(len(self.sheets)):
            wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (idx + 1, idx + 1))
        count = len(self.sheets)
        wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (count + 1))
        wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>' % (count + 2))
        wb_rels.append("</Relationships>")
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                "<dc:title>%s</dc:title><dc:creator>%s</dc:creator>"
                '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
                '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
                "</cp:coreProperties>") % (_text(self.title), _text(self.creator), now, now)
        titles = "".join("<vt:lpstr>%s</vt:lpstr>" % _text(s.name) for s in self.sheets)
        app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
               'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
               "<Application>Microsoft Excel</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
               '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>ワークシート</vt:lpstr></vt:variant>'
               "<vt:variant><vt:i4>%d</vt:i4></vt:variant></vt:vector></HeadingPairs>"
               '<TitlesOfParts><vt:vector size="%d" baseType="lpstr">%s</vt:vector></TitlesOfParts>'
               "<AppVersion>16.0300</AppVersion></Properties>") % (count, count, titles)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", "".join(content_types))
            zf.writestr("_rels/.rels", rels)
            zf.writestr("docProps/core.xml", core)
            zf.writestr("docProps/app.xml", app)
            zf.writestr("xl/workbook.xml", self._workbook_xml())
            zf.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))
            zf.writestr("xl/styles.xml", self._styles_xml())
            for idx, text in enumerate(sheets_xml):
                zf.writestr("xl/worksheets/sheet%d.xml" % (idx + 1), text)
            zf.writestr("xl/sharedStrings.xml", self._shared_xml())


def _abs_ref(ref):
    match = re.match(r"([A-Z]+)(\d+)", ref)
    return "$%s$%s" % (match.group(1), match.group(2))
