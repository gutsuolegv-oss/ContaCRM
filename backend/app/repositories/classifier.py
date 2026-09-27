from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models import (
    Periodicity,
    ReportCategory,
    ReportRule,
    ReportType,
    ReportTypeStep,
    Status,
    StatusSet,
)
from app.repositories.base import Repository


class CategoryRepository(Repository[ReportCategory]):
    model = ReportCategory

    async def list(self, is_active: bool | None = None) -> Sequence[ReportCategory]:
        stmt = select(ReportCategory).order_by(ReportCategory.sort_order, ReportCategory.id)
        if is_active is not None:
            stmt = stmt.where(ReportCategory.is_active.is_(is_active))
        return (await self.session.scalars(stmt)).all()


class StatusSetRepository(Repository[StatusSet]):
    model = StatusSet

    async def list(self) -> Sequence[StatusSet]:
        stmt = select(StatusSet).options(selectinload(StatusSet.statuses)).order_by(StatusSet.id)
        return (await self.session.scalars(stmt)).all()

    async def get_with_statuses(self, id_: int) -> StatusSet | None:
        stmt = (
            select(StatusSet)
            .where(StatusSet.id == id_)
            .options(selectinload(StatusSet.statuses))
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(stmt)).one_or_none()


class StatusRepository(Repository[Status]):
    model = Status


class ReportTypeRepository(Repository[ReportType]):
    model = ReportType

    async def list(
        self,
        category_id: int | None = None,
        periodicity: Periodicity | None = None,
        is_active: bool | None = None,
    ) -> Sequence[ReportType]:
        stmt = select(ReportType).order_by(
            ReportType.sort_order, ReportType.code, ReportType.valid_from
        )
        if category_id is not None:
            stmt = stmt.where(ReportType.category_id == category_id)
        if periodicity is not None:
            stmt = stmt.where(ReportType.periodicity == periodicity)
        if is_active is not None:
            stmt = stmt.where(ReportType.is_active.is_(is_active))
        return (await self.session.scalars(stmt)).all()

    async def list_by_ids(self, ids: set[int]) -> Sequence[ReportType]:
        if not ids:
            return []
        stmt = select(ReportType).where(ReportType.id.in_(ids)).order_by(ReportType.code)
        return (await self.session.scalars(stmt)).all()

    async def get_detail(self, id_: int) -> ReportType | None:
        stmt = (
            select(ReportType)
            .where(ReportType.id == id_)
            .options(selectinload(ReportType.steps), selectinload(ReportType.rules))
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(stmt)).one_or_none()


class StepRepository(Repository[ReportTypeStep]):
    model = ReportTypeStep


class RuleRepository(Repository[ReportRule]):
    model = ReportRule

    async def list_for_report_type(self, report_type_id: int) -> Sequence[ReportRule]:
        stmt = (
            select(ReportRule)
            .where(ReportRule.report_type_id == report_type_id)
            .order_by(ReportRule.priority.desc(), ReportRule.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_applicable(
        self, as_of: date, report_type_id: int | None = None
    ) -> Sequence[ReportRule]:
        """Regulile active ale tipurilor de raport active și valabile la data `as_of`."""
        stmt = (
            select(ReportRule)
            .join(ReportType, ReportType.id == ReportRule.report_type_id)
            .where(
                ReportRule.is_active.is_(True),
                ReportType.is_active.is_(True),
                ReportType.valid_from <= as_of,
                or_(ReportType.valid_to.is_(None), ReportType.valid_to >= as_of),
            )
        )
        if report_type_id is not None:
            stmt = stmt.where(ReportRule.report_type_id == report_type_id)
        return (await self.session.scalars(stmt)).all()
