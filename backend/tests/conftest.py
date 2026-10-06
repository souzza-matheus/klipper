import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_barberbot.db"
os.environ["EVOLUTION_URL"] = ""
os.environ["RUN_SCHEDULER"] = "false"
os.environ["DEV_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402


@pytest.fixture()
def db():
    from app.db import Base, SessionLocal, engine
    from app.seed import seed
    Base.metadata.drop_all(engine)
    seed(demo_finance=False)
    s = SessionLocal()
    yield s
    s.close()
