import base64, io, json, sqlite3, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont
db, port = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
rows = con.execute("select p.id, p.amount, c.phone, c.name from payments p join appointments a on a.id=p.appointment_id "
                   "join customers c on c.id=a.customer_id where p.status='pending' order by p.id").fetchall()
print(rows)
import collections; cnt = collections.Counter(r[2] for r in rows); pid, amount, phone, name = [r for r in rows if cnt[r[2]] == 1][0]
img = Image.new("RGB", (540, 900), "white")
d = ImageDraw.Draw(img)
try:
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26); fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except Exception:
    f = fb = ImageFont.load_default()
d.rectangle([0, 0, 540, 120], fill="#820AD1")
d.text((30, 40), "Comprovante de Pix", fill="white", font=f)
d.text((30, 170), f"R$ {amount}".replace(".", ","), fill="black", font=fb)
y = 260
for k, v in [("Para", "Barbearia Demo"), ("De", name), ("Data", "hoje"), ("ID", "E1234567820261020ABCDEF123456")]:
    d.text((30, y), k, fill="#666", font=f); d.text((30, y + 34), v, fill="black", font=f); y += 100
buf = io.BytesIO(); img.save(buf, "JPEG")
req = urllib.request.Request(f"http://127.0.0.1:{port}/dev/simulate-receipt", method="POST",
    data=json.dumps({"phone": phone, "base64": base64.b64encode(buf.getvalue()).decode(), "mimetype": "image/jpeg"}).encode(),
    headers={"Content-Type": "application/json", "X-Setup-Token": "audit-token"})
print(urllib.request.urlopen(req).read().decode()[:1500])
