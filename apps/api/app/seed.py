import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocumentModel, MenuItemModel

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def seed_menu_if_empty(session: Session) -> None:
    count = session.scalar(select(func.count()).select_from(MenuItemModel))
    if count:
        return

    menu_path = PROJECT_ROOT / "data" / "seed" / "menu.json"
    records = json.loads(menu_path.read_text(encoding="utf-8"))
    session.add_all(MenuItemModel(**record) for record in records)
    session.commit()


def seed_knowledge_if_empty(session: Session) -> None:
    count = session.scalar(select(func.count()).select_from(KnowledgeDocumentModel))
    if count:
        return

    knowledge_path = PROJECT_ROOT / "data" / "seed" / "knowledge.json"
    records = json.loads(knowledge_path.read_text(encoding="utf-8"))
    session.add_all(KnowledgeDocumentModel(**record) for record in records)
    session.commit()
