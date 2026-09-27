from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ClientReportType, ReportType
from app.repositories.base import Repository


class ClientReportTypeRepository(Repository[ClientReportType]):
    model = ClientReportType

    async def list_for_client(
        self, client_id: int, active_only: bool = False
    ) -> Sequence[ClientReportType]:
        stmt = (
            select(ClientReportType)
            .join(ReportType, ReportType.id == ClientReportType.report_type_id)
            .where(ClientReportType.client_id == client_id)
            .options(selectinload(ClientReportType.report_type))
            .order_by(ReportType.sort_order, ReportType.code, ClientReportType.valid_from)
        )
        if active_only:
            stmt = stmt.where(ClientReportType.is_active.is_(True))
        return (await self.session.scalars(stmt)).all()

    async def get_with_report_type(self, id_: int) -> ClientReportType | None:
        stmt = (
            select(ClientReportType)
            .where(ClientReportType.id == id_)
            .options(selectinload(ClientReportType.report_type))
        )
        return (await self.session.scalars(stmt)).one_or_none()
