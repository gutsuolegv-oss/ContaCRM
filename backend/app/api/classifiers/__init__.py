"""/api/classifiers — clasificatorul de rapoarte.

Citirea: orice utilizator autentificat. Scrierea și previzualizarea (care listează clienți):
admin și director (ClassifierEditor).
"""

from fastapi import APIRouter

from app.api.classifiers import categories, client_matrix, report_types, status_sets

router = APIRouter(prefix="/api/classifiers")
router.include_router(categories.router)
router.include_router(status_sets.router)
router.include_router(report_types.router)
router.include_router(client_matrix.router)
