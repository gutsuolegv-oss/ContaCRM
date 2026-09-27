from app.models import AuditLog
from app.repositories.base import Repository


class AuditRepository(Repository[AuditLog]):
    model = AuditLog
