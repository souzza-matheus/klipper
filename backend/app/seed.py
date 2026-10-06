"""Cria uma barbearia de demonstração. Uso: python -m app.seed"""
from datetime import time
from decimal import Decimal

from sqlalchemy import select

from .auth import hash_password
from .db import Base, SessionLocal, engine
from .models import Barber, Service, Shop, User, WorkingHour


def seed(owner_phone: str = "5531999990000") -> Shop:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        shop = db.scalar(select(Shop).where(Shop.evolution_instance == "barbearia-demo"))
        if shop:
            return shop
        shop = Shop(
            name="Barbearia Demo", address="Rua Exemplo, 123 - Centro, Conselheiro Lafaiete/MG",
            phone="(31) 3333-0000", owner_phone=owner_phone, instagram="@barbeariademo",
            evolution_instance="barbearia-demo", pix_enabled=True, pix_key="contato@barbeariademo.com.br",
            pix_key_type="email", pix_receiver_name="Barbearia Demo", pix_city="Cons Lafaiete",
        )
        db.add(shop)
        db.flush()
        db.add(User(shop_id=shop.id, name="Dono Demo", email="admin@demo.com", password_hash=hash_password("demo123")))
        corte = Service(shop_id=shop.id, name="Corte", duration_minutes=30, price=Decimal("40"), sort_order=1)
        barba = Service(shop_id=shop.id, name="Barba", duration_minutes=30, price=Decimal("30"), sort_order=2)
        combo = Service(shop_id=shop.id, name="Corte + Barba", duration_minutes=60, price=Decimal("65"), sort_order=3)
        db.add_all([corte, barba, combo])
        for name, phone in (("João", "5531988880001"), ("Pedro", "5531988880002")):
            b = Barber(shop_id=shop.id, name=name, phone=phone, services=[corte, barba, combo])
            for wd in range(0, 6):  # segunda a sábado
                b.working_hours.append(WorkingHour(weekday=wd, start=time(9), end=time(12)))
                if wd < 5:
                    b.working_hours.append(WorkingHour(weekday=wd, start=time(13), end=time(19)))
            db.add(b)
        db.commit()
        print("Barbearia demo criada. Login do app: admin@demo.com / demo123")
        return shop
    finally:
        db.close()


if __name__ == "__main__":
    seed()
