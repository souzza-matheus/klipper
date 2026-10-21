# Relógio fixo para o backend descartável da auditoria: hoje às 10:40 (avança com o tempo real a partir daí)
import sys, time
from datetime import datetime, timedelta
import app.config as cfg
_t0 = time.time()
def fake():
    base = datetime.now(cfg.TZ).replace(tzinfo=None, hour=10, minute=40, second=0, microsecond=0)
    return base + timedelta(seconds=int(time.time() - _t0))
cfg.now_local = fake
if sys.argv[1] == 'seed':
    sys.argv = ['seed_mock']
    from app import seed_mock; seed_mock.main()
else:
    import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')
