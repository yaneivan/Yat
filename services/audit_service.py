"""
Audit Log Service — логирование действий пользователей.

Записывает кто, что, когда и какие данные изменил.
"""

import json
from typing import Any, Dict, Optional
from database.session import SessionLocal
from database.models import AuditLog


class AuditService:
    """Сервис аудита изменений."""

    def log(
        self,
        user_id: Optional[int],
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        old_value: Any = None,
        new_value: Any = None,
        details: str = '',
    ) -> Optional[Dict]:
        """Записать запись в audit log."""
        session = SessionLocal()
        try:
            log = AuditLog(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                details=details,
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log.to_dict()
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def get_logs(
        self,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """Получить записи аудита с фильтрацией."""
        session = SessionLocal()
        try:
            query = session.query(AuditLog)

            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            if entity_type:
                query = query.filter_by(entity_type=entity_type)
            if entity_id is not None:
                query = query.filter_by(entity_id=entity_id)
            if action:
                query = query.filter_by(action=action)

            query = query.order_by(AuditLog.created_at.desc())
            logs = query.limit(limit).offset(offset).all()

            return [log.to_dict() for log in logs]
        finally:
            session.close()

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Статистика по действиям пользователя."""
        session = SessionLocal()
        try:
            from sqlalchemy import func

            total = session.query(AuditLog).filter_by(user_id=user_id).count()

            by_action = dict(
                session.query(AuditLog.action, func.count(AuditLog.id))
                .filter_by(user_id=user_id)
                .group_by(AuditLog.action)
                .all()
            )

            by_entity = dict(
                session.query(AuditLog.entity_type, func.count(AuditLog.id))
                .filter_by(user_id=user_id)
                .group_by(AuditLog.entity_type)
                .all()
            )

            return {
                'user_id': user_id,
                'total_actions': total,
                'by_action': by_action,
                'by_entity_type': by_entity,
            }
        finally:
            session.close()


# Global instance
audit_service = AuditService()
