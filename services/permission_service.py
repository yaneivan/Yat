"""
Permission Service — управление правами доступа к проектам.

Логика:
- is_admin=True → видит все проекты, полный доступ
- is_admin=False → видит только назначенные проекты
  - project_permissions.role='read' → только просмотр
  - project_permissions.role='write' → полный доступ к проекту
"""

from typing import Dict, List, Optional
from database.session import SessionLocal
from database.models import ProjectPermission, Project, User


class PermissionService:
    """Управление правами пользователей на проекты."""

    def grant_access(self, user_id: int, project_name: str, role: str = 'write') -> Optional[Dict]:
        """Дать пользователю доступ к проекту. role: 'read' или 'write'."""
        session = SessionLocal()
        try:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return None

            # Upsert
            existing = session.query(ProjectPermission).filter_by(
                user_id=user_id, project_id=project.id
            ).first()
            if existing:
                existing.role = role
            else:
                perm = ProjectPermission(user_id=user_id, project_id=project.id, role=role)
                session.add(perm)

            session.commit()
            return {'user_id': user_id, 'project': project_name, 'role': role}
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def revoke_access(self, user_id: int, project_name: str) -> bool:
        """Отозвать доступ к проекту."""
        session = SessionLocal()
        try:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return False

            perm = session.query(ProjectPermission).filter_by(
                user_id=user_id, project_id=project.id
            ).first()
            if not perm:
                return False

            session.delete(perm)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def get_user_permissions(self, user_id: int) -> List[Dict]:
        """Все права пользователя."""
        session = SessionLocal()
        try:
            perms = session.query(ProjectPermission).filter_by(user_id=user_id).all()
            result = []
            for perm in perms:
                project = session.query(Project).filter_by(id=perm.project_id).first()
                if project:
                    result.append({
                        'project_name': project.name,
                        'role': perm.role,
                    })
            return result
        finally:
            session.close()

    def get_project_permissions(self, project_name: str) -> List[Dict]:
        """Все пользователи с доступом к проекту."""
        session = SessionLocal()
        try:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return []

            perms = session.query(ProjectPermission).filter_by(project_id=project.id).all()
            result = []
            for perm in perms:
                user = session.query(User).filter_by(id=perm.user_id).first()
                if user:
                    result.append({
                        'user_id': user.id,
                        'username': user.username,
                        'role': perm.role,
                    })
            return result
        finally:
            session.close()

    def can_access_project(self, user_id: int, project_name: str) -> bool:
        """Проверка: есть ли у пользователя доступ к проекту."""
        session = SessionLocal()
        try:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return False

            perm = session.query(ProjectPermission).filter_by(
                user_id=user_id, project_id=project.id
            ).first()
            return perm is not None
        finally:
            session.close()

    def get_project_role(self, user_id: int, project_name: str) -> Optional[str]:
        """Вернуть роль пользователя в проекте: 'read', 'write' или None."""
        session = SessionLocal()
        try:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return None

            perm = session.query(ProjectPermission).filter_by(
                user_id=user_id, project_id=project.id
            ).first()
            return perm.role if perm else None
        finally:
            session.close()

    def get_accessible_projects(self, user_id: int) -> List[str]:
        """Список проектов, доступных пользователю."""
        session = SessionLocal()
        try:
            perms = session.query(ProjectPermission).filter_by(user_id=user_id).all()
            result = []
            for perm in perms:
                project = session.query(Project).filter_by(id=perm.project_id).first()
                if project:
                    result.append(project.name)
            return result
        finally:
            session.close()


# Global instance
permission_service = PermissionService()
