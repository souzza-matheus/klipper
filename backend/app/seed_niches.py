"""Cria uma empresa de demonstração para cada segmento, com dados de teste (clientes, agenda de 30 dias para trás
e 7 para frente, Pix, avaliações, bloqueios, gastos, cliente bloqueado, cliente em aprovação e par incompatível).

Uso:
    python -m app.seed_niches           # cria as empresas que faltam (a barbearia vem de app.seed / app.seed_mock)
    python -m app.seed_niches --reset   # apaga os dados mock dessas empresas e gera de novo

Login de cada uma: senha demo123 (e-mails no fim da execução). As empresas não têm WhatsApp do dono nem dos
profissionais, para nenhum alerta sair para números reais.
"""
import argparse
import random
from datetime import time
from decimal import Decimal

from sqlalchemy import func, select

from .auth import hash_password
from .config import now_local
from .db import SessionLocal
from .models import (
    AccessStatus, Appointment, ApptStatus, Barber, ConflictAction, CustomerConflict, Membership, Role, Service, Shop,
    User, WorkingHour,
)
from .seed import seed, seed_finance
from .seed_crm import seed_crm
from .seed_mock import (
    _book, _future_weekdays, apply_statuses, create_appointments, create_blocks, create_customers, create_payments,
    create_reviews, reset_mock, set_payment_methods, summary,
)

FEMALE = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela", "Júlia",
          "Larissa", "Mariana", "Natália", "Patrícia", "Renata", "Sabrina", "Tatiane", "Vanessa", "Yasmin", "Letícia"]
MIXED = FEMALE + ["Lucas", "Gabriel", "Rafael", "Matheus", "Gustavo", "Felipe", "Bruno", "Thiago", "André",
                  "Carlos", "Eduardo", "Marcelo", "Fernando", "Ricardo", "Daniel"]

# Expediente: (dias da semana 0 = segunda, [(início, fim), ...])
PROFILES = [
    {
        "niche": "beauty", "instance": "salao-demo", "email": "salao@demo.com", "owner": "Dona Salão Demo",
        "name": "Studio Bella Beleza & Estética", "address": "Av. das Flores, 450 - Centro", "instagram": "@studiobella",
        "pix_key": "contato@studiobella.com.br",
        "services": [("Escova", 45, "60", 25), ("Corte feminino", 60, "90", 20), ("Coloração", 120, "180", 10),
                     ("Manicure e pedicure", 60, "55", 25), ("Design de sobrancelha", 30, "40", 15),
                     ("Limpeza de pele", 60, "120", 5)],
        "pros": ["Ana Paula", "Carla", "Juliana"],
        "hours": ([1, 2, 3, 4, 5], [(time(9), time(12)), (time(13), time(19))]),
        "first_names": FEMALE,
        "notes": ["Cabelo com química: não usar chapinha acima de 180 °C.", "Alérgica a esmalte com formol.",
                  "Prefere a Juliana para as unhas.", "Sempre pede café sem açúcar.",
                  "Fazendo transição capilar, só cortar as pontas."],
        "appt_notes": ["Vai trazer foto da cor desejada.", "Retoque de raiz.", "Unhas em gel."],
        "comments": (["Amei o resultado!", "Atendimento impecável.", "Cabelo ficou lindo, obrigada!"],
                     ["Gostei, mas atrasou um pouco.", "Bom, achei o preço salgado."],
                     ["A cor não ficou como pedi.", "Esperei muito para ser atendida."]),
        "one_off": [("Produtos de coloração", "produtos", "620.00", 3), ("Esmaltes e acetona", "produtos", "180.00", 12),
                    ("Impulsionamento no Instagram", "marketing", "150.00", 22)],
        "extras": (("Manutenção do secador", "manutencao", "160.00"), ("Toalhas descartáveis", "produtos", "95.00")),
        "blocked": ("Faltou 4 vezes e não atende o telefone.",),
        "approval": ("Remarca sempre em cima da hora.",),
        "conflict": ("Ex-sócias, pediram para não se encontrarem no salão.", ConflictAction.APPROVAL),
    },
    {
        "niche": "petshop", "instance": "petshop-demo", "email": "pet@demo.com", "owner": "Dono Pet Demo",
        "name": "Pet Feliz Banho e Tosa", "address": "Rua dos Bichos, 77 - Jardim", "instagram": "@petfeliz",
        "pix_key": "contato@petfeliz.com.br",
        "services": [("Banho porte pequeno", 60, "50", 30), ("Banho e tosa", 90, "85", 30), ("Tosa higiênica", 45, "40", 15),
                     ("Consulta veterinária", 30, "150", 15), ("Vacinação", 30, "90", 10)],
        "pros": ["Marcos (tosador)", "Dra. Paula (veterinária)", "Rita (banhista)"],
        "hours": ([0, 1, 2, 3, 4, 5], [(time(8), time(12)), (time(13), time(18))]),
        "first_names": MIXED,
        "notes": ["Tutor do Thor (golden, 6 anos): muito agitado no secador.", "Mel (poodle) tem alergia a shampoo perfumado.",
                  "Bob é idoso, banho rápido e sem tosa na máquina.", "Luna precisa de focinheira.",
                  "Vacina antirrábica do Max vence no mês que vem."],
        "appt_notes": ["Corte de unhas também.", "Tosa na tesoura.", "Trazer a carteira de vacinação."],
        "comments": (["Meu cachorro voltou cheiroso e feliz!", "Equipe muito carinhosa.", "Tosa perfeita."],
                     ["Bom, mas demorou para buscar.", "Ok, poderiam mandar foto durante o banho."],
                     ["Cortaram a unha muito curta.", "Atrasou mais de uma hora."]),
        "one_off": [("Shampoos e condicionadores", "produtos", "540.00", 3), ("Vacinas", "produtos", "900.00", 10),
                    ("Anúncio em grupo do bairro", "marketing", "80.00", 22)],
        "extras": (("Conserto da banheira", "manutencao", "350.00"), ("Toalhas e laços", "equipamentos", "120.00")),
        "blocked": ("Deixou o pet além do horário várias vezes e não pagou o último banho.",),
        "approval": ("Cachorro agressivo: confirmar se a equipe com focinheira está disponível.",),
        "conflict": ("Os cachorros brigaram na recepção.", ConflictAction.BLOCK),
    },
    {
        "niche": "clinic", "instance": "clinica-demo", "email": "clinica@demo.com", "owner": "Dona Clínica Demo",
        "name": "Clínica Vida Plena", "address": "Rua da Saúde, 210 - sala 3", "instagram": "@clinicavidaplena",
        "pix_key": "financeiro@vidaplena.com.br",
        "services": [("Consulta clínica geral", 30, "200", 35), ("Retorno", 20, "80", 20), ("Fisioterapia", 50, "120", 20),
                     ("Nutrição", 45, "180", 15), ("Psicoterapia", 50, "160", 10)],
        "pros": ["Dr. Ricardo Lima", "Dra. Fernanda Costa", "Dra. Helena Souza"],
        "hours": ([0, 1, 2, 3, 4], [(time(8), time(12)), (time(13), time(18))]),
        "first_names": MIXED,
        "notes": ["Hipertenso, trazer a última medição de pressão.", "Alergia a dipirona.",
                  "Prefere atendimento no fim da tarde.", "Pós-operatório de joelho, fisioterapia 2x por semana.",
                  "Gestante, 20 semanas."],
        "appt_notes": ["Trazer exames de sangue.", "Primeira consulta.", "Revisão do plano alimentar."],
        "comments": (["Médico muito atencioso.", "Atendimento pontual e cuidadoso.", "Recomendo a clínica."],
                     ["Bom, mas a recepção demorou.", "Ok, a sala de espera estava cheia."],
                     ["Esperei 40 minutos além do horário.", "Consulta muito rápida."]),
        "one_off": [("Material de consultório", "produtos", "420.00", 3), ("Sistema de prontuário", "internet", "199.00", 8),
                    ("Anúncio no Google", "marketing", "300.00", 22)],
        "extras": (("Manutenção do ar-condicionado", "manutencao", "280.00"), ("Lençóis descartáveis", "produtos", "140.00")),
        "blocked": ("Comportamento agressivo com a recepção.",),
        "approval": ("Plano de saúde em análise: confirmar antes.",),
        "conflict": ("Processo judicial entre os dois: não deixar na sala de espera juntos.", ConflictAction.BLOCK),
    },
    {
        "niche": "fitness", "instance": "estudio-demo", "email": "estudio@demo.com", "owner": "Dono Estúdio Demo",
        "name": "Estúdio Movimento Pilates & Funcional", "address": "Av. Brasil, 1500 - 2º andar",
        "instagram": "@estudiomovimento", "pix_key": "contato@estudiomovimento.com.br",
        "services": [("Aula de pilates", 50, "70", 40), ("Treino funcional", 50, "60", 30), ("Personal training", 60, "120", 20),
                     ("Avaliação física", 40, "90", 10)],
        "pros": ["Bruno", "Camila", "Diego"],
        "hours": ([0, 1, 2, 3, 4], [(time(6), time(12)), (time(15), time(21))]),
        "first_names": MIXED,
        "notes": ["Hérnia de disco L4-L5: evitar flexão com carga.", "Treina para meia maratona.",
                  "Prefere aulas às 6 h.", "Gestante, liberada pela obstetra para pilates.", "Lesão no ombro direito."],
        "appt_notes": ["Foco em mobilidade.", "Reavaliação mensal.", "Trazer tênis de treino."],
        "comments": (["Aula excelente, saí renovada!", "Professor muito atencioso.", "Melhor estúdio da cidade."],
                     ["Boa aula, mas a turma estava cheia.", "Ok, poderia ter mais variação."],
                     ["Aula começou atrasada.", "Ar-condicionado não funcionava."]),
        "one_off": [("Molas do reformer", "equipamentos", "480.00", 3), ("Kettlebells", "equipamentos", "650.00", 12),
                    ("Impulsionamento no Instagram", "marketing", "150.00", 22)],
        "extras": (("Manutenção da esteira", "manutencao", "220.00"), ("Toalhas e tapetes", "equipamentos", "160.00")),
        "blocked": ("Três mensalidades em atraso.",),
        "approval": ("Precisa de liberação médica antes de cada aula.",),
        "conflict": ("Discussão na aula em grupo.", ConflictAction.APPROVAL),
    },
]
PASSWORD = "demo123"


def create_shop(db, p) -> Shop:
    shop = Shop(name=p["name"], address=p["address"], phone="", owner_phone="", instagram=p["instagram"],
                evolution_instance=p["instance"], niche=p["niche"], theme_mode="auto", pix_enabled=True,
                pix_key=p["pix_key"], pix_key_type="email", pix_receiver_name=p["name"][:25], pix_city="Cons Lafaiete")
    db.add(shop)
    db.flush()
    db.add(User(shop_id=shop.id, name=p["owner"], email=p["email"], password_hash=hash_password(PASSWORD)))
    services = []
    for i, (name, minutes, price, _) in enumerate(p["services"], 1):
        services.append(Service(shop_id=shop.id, name=name, duration_minutes=minutes, price=Decimal(price), sort_order=i))
    db.add_all(services)
    weekdays, ranges = p["hours"]
    for name in p["pros"]:
        b = Barber(shop_id=shop.id, name=name, phone="", services=services)
        for wd in weekdays:
            for start, end in ranges:
                b.working_hours.append(WorkingHour(weekday=wd, start=start, end=end))
        db.add(b)
    db.commit()
    return shop


def access_demo(db, shop, p, customers, barbers, services, weights, today, now) -> None:
    """Um cliente bloqueado, um que precisa de aprovação (com um pedido pendente) e um par incompatível."""
    blocked, approval, x, y = customers[-4:]
    blocked.access_status, blocked.access_reason, blocked.access_changed_at = AccessStatus.BLOCKED, p["blocked"][0], now
    approval.access_status, approval.access_reason, approval.access_changed_at = AccessStatus.APPROVAL, p["approval"][0], now
    notes, action = p["conflict"]
    a, b = sorted((x.id, y.id))
    db.add(CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, notes=notes, conflict_action=action))
    db.flush()
    for day in _future_weekdays(today):
        appt = _book(db, shop, approval, barbers, services, day, weights, [])
        if appt:
            appt.status, appt.created_at, appt.approval_requested_at = ApptStatus.PENDING_APPROVAL, now, now
            break
    db.commit()


MULTI_EMAIL = "duas.empresas@demo.com"


def ensure_multi_business(db) -> None:
    """Uma conta que entra em dois negócios (dona da Barbearia Demo e recepção no salão), para testar a tela
    "Escolha o negócio" e Mais > Trocar de negócio."""
    shops = {s.evolution_instance: s for s in db.scalars(select(Shop))}
    targets = [(shops.get("barbearia-demo"), Role.OWNER), (shops.get(PROFILES[0]["instance"]), Role.RECEPTION)]
    if not all(shop for shop, _ in targets):
        return
    user = db.scalar(select(User).where(User.email == MULTI_EMAIL))
    if user is None:
        user = User(name="Conta com dois negócios", email=MULTI_EMAIL, password_hash=hash_password(PASSWORD))
        db.add(user)
    have = {m.shop_id for m in user.memberships}
    for shop, role in targets:
        if shop.id not in have:
            user.memberships.append(Membership(shop_id=shop.id, role=role, active=True))
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria uma empresa de demonstração para cada segmento.")
    parser.add_argument("--reset", action="store_true", help="apaga os dados mock dessas empresas e gera de novo")
    args = parser.parse_args()

    seed()  # garante o esquema e a barbearia demo (os dados dela vêm de python -m app.seed_mock)
    db = SessionLocal()
    try:
        for i, p in enumerate(PROFILES):
            random.seed(100 + i)
            shop = db.scalar(select(Shop).where(Shop.evolution_instance == p["instance"]))
            if shop is None:
                shop = create_shop(db, p)
                print(f"Criada: {shop.name}")
            elif args.reset:
                reset_mock(db, shop)
            elif db.scalar(select(func.count()).select_from(Appointment).where(Appointment.shop_id == shop.id)):
                print(f"{shop.name} já tem dados (use --reset para gerar de novo).")
                continue

            now = now_local()
            today = now.date()
            barbers = sorted((b for b in shop.barbers if b.active), key=lambda b: b.id)
            services = {s.name: s for s in shop.services}
            weights = {name: w for name, _, _, w in p["services"]}

            customers = create_customers(db, shop, now, p["first_names"], p["notes"])
            create_blocks(db, shop, barbers, today)
            appts = create_appointments(db, shop, customers[:-4], barbers, services, today, weights, p["appt_notes"])
            apply_statuses(appts, shop, now)
            create_payments(db, shop, appts, now)
            set_payment_methods(appts)
            create_reviews(db, shop, appts, now, p["comments"])
            db.commit()
            access_demo(db, shop, p, customers, barbers, services, weights, today, now)
            seed_finance(db, shop, today, p["one_off"], p["extras"])
            seed_crm(db, shop, now_local(), "." + p["email"].split("@", 1)[0], random.Random(200 + i))
            summary(db, shop)
        ensure_multi_business(db)
    finally:
        db.close()

    print("\nLogins (senha demo123). Equipe: recepcao[.empresa]@demo.com e profissional[.empresa]@demo.com, ex.: recepcao.salao@demo.com:")
    print("  barbershop  admin@demo.com")
    for p in PROFILES:
        print(f"  {p['niche']:<11} {p['email']}")
    print(f"  dois negócios (barbearia e salão): {MULTI_EMAIL}")


if __name__ == "__main__":
    main()
