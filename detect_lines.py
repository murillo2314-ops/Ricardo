"""
Parse the raw PDF content stream to find horizontal lines (form field underlines).
Uses PyPDF2 only (no cryptography dependency).
"""
import re
from PyPDF2 import PdfReader

PDF_PATH = "/root/.claude/uploads/0d02e5e2-ce91-4400-86cb-d3f06e9edb35/be5a81df-KYC_ProAstra_.pdf"

reader = PdfReader(PDF_PATH)
page = reader.pages[0]

# Get raw content stream
content = page.get_contents()
if hasattr(content, 'get_data'):
    raw = content.get_data()
elif hasattr(content, 'get_object'):
    obj = content.get_object()
    if hasattr(obj, 'get_data'):
        raw = obj.get_data()
    else:
        raw = b""
else:
    raw = b""

text = raw.decode('latin-1', errors='replace')

# Parse PDF drawing operations
# Look for: x y m (moveto), x y l (lineto), S or s (stroke)
# And: x y w h re (rectangle)
# We'll collect path segments

lines_found = []
rects_found = []

# Tokenize
tokens = text.split()

i = 0
path = []
while i < len(tokens):
    tok = tokens[i]

    if tok == 'm' and i >= 2:
        try:
            x, y = float(tokens[i-2]), float(tokens[i-1])
            path = [(x, y)]
        except:
            pass

    elif tok == 'l' and i >= 2:
        try:
            x, y = float(tokens[i-2]), float(tokens[i-1])
            path.append((x, y))
        except:
            pass

    elif tok in ('S', 's', 'f', 'F', 'B', 'b') and len(path) >= 2:
        # Stroke the path — check each segment
        for j in range(len(path) - 1):
            x0, y0 = path[j]
            x1, y1 = path[j+1]
            if abs(y1 - y0) < 1.5 and (x1 - x0) > 20:  # horizontal
                lines_found.append((x0, y0, x1, y1))
        path = []

    elif tok == 're' and i >= 4:
        try:
            x = float(tokens[i-4])
            y = float(tokens[i-3])
            w = float(tokens[i-2])
            h = float(tokens[i-1])
            if h < 3 and w > 20:  # thin horizontal rect = underline
                rects_found.append((x, y, x+w, y+h))
        except:
            pass

    i += 1

all_lines = sorted(set(lines_found + rects_found), key=lambda l: -l[1])

print(f"Page mediabox: {page.mediabox}")
print(f"\nFound {len(all_lines)} horizontal lines/underlines:\n")

for idx, (x0, y0, x1, y1) in enumerate(all_lines):
    print(f"  [{idx:2d}]  y={y0:7.2f}  x0={x0:7.2f}  x1={x1:7.2f}  width={x1-x0:7.2f}")

# Also extract text with positions (BT/ET blocks)
print("\n--- Text blocks in PDF ---")
bt_blocks = re.findall(r'BT(.*?)ET', text, re.DOTALL)
for block in bt_blocks:
    # Find Td/TD/Tm positioning and Tj/TJ text
    positions = re.findall(r'([-\d.]+)\s+([-\d.]+)\s+T[dm]', block)
    texts = re.findall(r'\((.*?)\)\s*Tj', block)
    tj_arr = re.findall(r'\[(.*?)\]\s*TJ', block)
    if texts or tj_arr:
        pos_str = str(positions[-1]) if positions else "?"
        print(f"  pos={pos_str}  texts={texts}  TJ={tj_arr[:1]}")
