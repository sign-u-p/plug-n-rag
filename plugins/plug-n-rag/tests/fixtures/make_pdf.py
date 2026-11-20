"""Generate a tiny PDF with a real text layer (two pages, German text) without extra libraries.

Run: python tests/fixtures/make_pdf.py <output.pdf>
"""

import sys

PAGES = [
    [
        "Leitlinie Ergotherapie bei Kindern",
        "Kapitel 1: Betätigungsorientierte Befunderhebung",
        "Die Befunderhebung beginnt mit einem Gespräch über die Betätigungen,",
        "die dem Kind und der Familie wichtig sind. Standardisierte Tests ergänzen",
        "die Beobachtung, ersetzen sie aber nicht.",
    ],
    [
        "Kapitel 2: Hilfsmittelversorgung",
        "Bei der Hilfsmittelversorgung zählt, ob das Hilfsmittel im Alltag wirklich",
        "genutzt wird. Ein Rollstuhl, eine Sitzschale oder ein angepasstes Besteck",
        "werden gemeinsam mit der Familie erprobt. Die Hilfsmittelberatung umfasst",
        "auch die Finanzierung durch die Krankenkasse.",
    ],
]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build() -> bytes:
    objs = []
    n_pages = len(PAGES)
    # 1 catalog, 2 pages, 3 font, 4 info, then per page: page obj + content obj
    page_ids = [5 + 2 * i for i in range(n_pages)]
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Title (Leitlinie Ergotherapie) /Author (Testautorin) >>")
    for i, lines in enumerate(PAGES):
        content = "BT /F1 12 Tf 72 760 Td 16 TL\n"
        for ln in lines:
            content += f"({esc(ln)}) Tj T*\n"
        content += "ET"
        data = content.encode("cp1252")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode()
        )
        objs.append(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for num, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    with open(sys.argv[1], "wb") as fh:
        fh.write(build())
