"""STEP Industrial Audit document service."""

# Registra rotas de auditoria com limites, concorrência controlada e contingência.
# O módulo usa o mesmo objeto FastAPI de main e as funções de IA são resolvidas
# dinamicamente, permitindo que ai_resilience aplique seus patches em seguida.
from . import ai_bounded_routes as _ai_bounded_routes  # noqa: F401,E402
