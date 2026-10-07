import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_barberbot.db"
os.environ["EVOLUTION_URL"] = ""
os.environ["RUN_SCHEDULER"] = "false"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "segredo-de-teste-com-mais-de-32-caracteres"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bcrypt  # noqa: E402
import pytest  # noqa: E402

# Nos testes, bcrypt com custo baixo (o mesmo algoritmo; só mais rápido). Produção usa o padrão (12).
_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _gensalt(4, prefix)


@pytest.fixture()
def db():
    from app.db import Base, SessionLocal, engine
    from app.seed import seed
    Base.metadata.drop_all(engine)
    seed(demo_finance=False, demo_customers=False)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    """O limite de tentativas de login é global (em memória): cada teste começa do zero."""
    from app.security import login_limiter
    login_limiter.reset()
    yield
