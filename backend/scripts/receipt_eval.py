"""Roda os comprovantes FICTÍCIOS (tests/fixtures/receipts/generate.py) no Gemini de verdade e imprime os campos
lidos, o resultado das conferências e o custo.

Uso (na pasta backend, com GEMINI_API_KEY no .env):
    python scripts/receipt_eval.py
    python scripts/receipt_eval.py --only correto injecao      # só alguns casos
    python scripts/receipt_eval.py --sleep 6                   # pausa entre casos (limite por minuto do plano gratuito)
    python scripts/receipt_eval.py --price-in 0.75 --price-out 3.75

Preços padrão: gemini-3.8-flash no plano pago (os mesmos do scripts/ai_eval.py): entrada US$ 0,75 e saída (inclui
thinking) US$ 3,75 por 1 milhão de tokens. Uma imagem conta como entrada.

Não usa o banco de desenvolvimento: cria um SQLite temporário com a Barbearia Demo (app.seed), força o modo simulação
do WhatsApp (nada sai) e guarda os arquivos numa pasta temporária. As imagens são geradas na hora com o horário atual,
para a conferência de data fazer sentido. Cada caso tem o próprio cliente com um Pix pendente de R$ 65,00 (Corte +
Barba) gerado há 30 minutos.
"""
import argparse
import base64
import os
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests" / "fixtures" / "receipts"))

TMP = Path(tempfile.mkdtemp(prefix="receipt-eval-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'eval.db'}"
os.environ["RECEIPTS_DIR"] = str(TMP / "files")
os.environ["EVOLUTION_URL"] = ""
os.environ["RUN_SCHEDULER"] = "false"

from sqlalchemy import select  # noqa: E402

from app.ai.usage import provider_configured  # noqa: E402
from app.config import now_local, settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AIUsage, Appointment, Barber, Customer, OutboxMessage, Service, Shop  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import payments, receipts  # noqa: E402
from generate import build_all  # noqa: E402

EXPECTED = {  # o que cada caso deveria dar
    "correto": "confere", "correto_pdf": "confere", "valor_diferente": "divergente",
    "recebedor_diferente": "divergente", "data_antiga": "divergente", "agendamento": "divergente",
    "foto_qualquer": "ilegivel", "injecao": "divergente",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sleep", type=float, default=0)
    ap.add_argument("--price-in", type=float, default=0.75)
    ap.add_argument("--price-out", type=float, default=3.75)
    args = ap.parse_args()
    if not provider_configured():
        sys.exit("GEMINI_API_KEY não configurada no backend/.env")

    seed(demo_finance=False, demo_customers=False)
    db = SessionLocal()
    shop = db.scalar(select(Shop))
    shop.ai_allow_free_tier = True  # dados fictícios: pode rodar no plano gratuito
    db.commit()
    barber = db.scalar(select(Barber).where(Barber.shop_id == shop.id).order_by(Barber.id))
    combo = db.scalar(select(Service).where(Service.name == "Corte + Barba"))
    files = build_all(TMP / "imgs", now_local())
    names = [n for n in files if not args.only or n in args.only]
    print(f"Modelo: {settings.ai_model} (reserva {settings.ai_fallback_model}) | plano {settings.ai_tier}\n")

    total_in = total_out = 0
    hits = 0
    for i, name in enumerate(names):
        phone = f"55000900000{i:02d}"
        c = Customer(shop_id=shop.id, phone=phone, name=f"Cliente Fictício {i}")
        db.add(c)
        db.flush()
        start = now_local().replace(second=0) + timedelta(days=1, hours=i)
        a = Appointment(shop_id=shop.id, customer_id=c.id, barber_id=barber.id, service_id=combo.id, start=start,
                        end=start + timedelta(minutes=combo.duration_minutes), price=combo.price)
        db.add(a)
        db.flush()
        pay = payments.get_or_create_pix(db, shop, a)
        pay.created_at = now_local() - timedelta(minutes=30)
        db.commit()

        data = files[name].read_bytes()
        mime = "application/pdf" if name.endswith("pdf") else "image/png"
        last_usage = db.scalar(select(AIUsage.id).order_by(AIUsage.id.desc()).limit(1)) or 0
        last_msg = db.scalar(select(OutboxMessage.id).order_by(OutboxMessage.id.desc()).limit(1)) or 0
        t0 = time.monotonic()
        r = receipts.handle_media(db, shop, phone, {"base64": base64.b64encode(data).decode(), "mimetype": mime})
        secs = time.monotonic() - t0
        uses = db.scalars(select(AIUsage).where(AIUsage.id > last_usage)).all()
        tin = sum(u.input_tokens for u in uses)
        tout = sum(u.output_tokens + u.thinking_tokens for u in uses)
        total_in, total_out = total_in + tin, total_out + tout
        cost = tin * args.price_in / 1e6 + tout * args.price_out / 1e6

        ok = r is not None and r.result == EXPECTED.get(name)
        hits += ok
        print(f"=== {name} ({len(data) // 1024} KB, {secs:.1f}s) -> {r.result if r else '-'} "
              f"{'OK' if ok else 'ESPERADO ' + EXPECTED.get(name, '?')}")
        if r is not None:
            print(f"  lido: valor={r.amount} data={r.paid_at} recebedor={r.receiver_name!r} chave={r.receiver_key!r}"
                  f"\n        banco_receb={r.receiver_bank!r} pagador={r.payer_name!r} banco_pag={r.payer_bank!r}"
                  f"\n        e2e={r.e2e_read!r} tipo={r.doc_type} confiança={r.confidence} leitura={r.read_status}")
            for ch in r.checks or []:
                print(f"  {'✔' if ch['ok'] else '✘'} {ch['label']}: {ch['detail']}")
        for m in db.scalars(select(OutboxMessage).where(OutboxMessage.id > last_msg,
                                                        OutboxMessage.phone == shop.owner_phone)):
            print("  dono: " + m.text.replace("\n", "\n        "))
        errors = [u.error for u in uses if not u.ok]
        print(f"  tokens: entrada {tin}, saída+raciocínio {tout} | US$ {cost:.5f}"
              + (f" | erros: {errors}" if errors else "") + "\n")
        if args.sleep and i + 1 < len(names):
            time.sleep(args.sleep)

    cost = total_in * args.price_in / 1e6 + total_out * args.price_out / 1e6
    n = len(names)
    print(f"Resumo: {hits}/{n} com o resultado esperado | entrada {total_in} e saída {total_out} tokens | "
          f"US$ {cost:.4f} no total, US$ {cost / max(n, 1):.5f} por comprovante")
    db.close()


if __name__ == "__main__":
    main()
