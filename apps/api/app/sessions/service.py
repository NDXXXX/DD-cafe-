import secrets

from sqlalchemy.orm import Session

from app.db.models import SessionModel


class SessionService:
    """Issues and looks up the server-issued token bound to a customer session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_token(self, session_id: str) -> str:
        model = self.session.get(SessionModel, session_id)
        if model is None:
            model = SessionModel(session_id=session_id, token=secrets.token_urlsafe(32))
            self.session.add(model)
            self.session.commit()
        return model.token
