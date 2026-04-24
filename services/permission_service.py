"""
Permission Service — управление правами доступа к проектам.

Логика:
- is_admin=True → видит все проекты, полный доступ
- is_admin=False → видит только назначенные проекты
  - role='viewer' → только просмотр
  - role='annotator' → рисовать, распознавать, сохранять
  - role='project_admin' → annotator + загрузка/удаление/batch/import
"""

from typing import Dict, List, Optional
from database.session import SessionLocal
from database.models import ProjectPermission, Project, User


class PermissionService:
    """Управление правами пользователей на проекты."""

    def grant_access(
        self, user_id: int, project_id: int, role: str = "annotator"
    ) -> Optional[Dict]:
        """
        Дать пользователю доступ к проекту по ID.
        role: 'viewer', 'annotator', 'project_admin'.
        """
        session = SessionLocal()
        try:
            project = session.get(Project, project_id)
            if not project:
                return None

            existing = (
                session.query(ProjectPermission)
                .filter_by(user_id=user_id, project_id=project.id)
                .first()
            )
            if existing:
                existing.role = role
            else:
                perm = ProjectPermission(
                    user_id=user_id, project_id=project.id, role=role
                )
                session.add(perm)

            session.commit()
            return {
                "user_id": user_id,
                "project_id": project.id,
                "project_name": project.name,
                "role": role,
            }
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def revoke_access_by_id(self, user_id: int, project_id: int) -> bool:
        """Отозвать доступ к проекту по ID."""
        session = SessionLocal()
        try:
            perm = (
                session.query(ProjectPermission)
                .filter_by(user_id=user_id, project_id=project_id)
                .first()
            )
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
                    result.append(
                        {
                            "project_id": project.id,
                            "project_name": project.name,
                            "role": perm.role,
                        }
                    )
            return result
        finally:
            session.close()

    def get_project_permissions_by_id(self, project_id: int) -> List[Dict]:
        """Все пользователи с доступом к проекту по ID."""
        session = SessionLocal()
        try:
            perms = (
                session.query(ProjectPermission).filter_by(project_id=project_id).all()
            )
            result = []
            for perm in perms:
                user = session.query(User).filter_by(id=perm.user_id).first()
                if user:
                    result.append(
                        {
                            "user_id": user.id,
                            "username": user.username,
                            "role": perm.role,
                        }
                    )
            return result
        finally:
            session.close()

    def can_access_project(self, user_id: int, project_id: int) -> bool:
        """Проверка: есть ли у пользователя доступ к проекту по ID."""
        session = SessionLocal()
        try:
            perm = (
                session.query(ProjectPermission)
                .filter_by(user_id=user_id, project_id=project_id)
                .first()
            )
            return perm is not None
        finally:
            session.close()

    def get_project_role(self, user_id: int, project_id: int) -> Optional[str]:
        """Вернуть роль пользователя в проекте по ID: 'viewer', 'annotator', 'project_admin' или None."""
        session = SessionLocal()
        try:
            perm = (
                session.query(ProjectPermission)
                .filter_by(user_id=user_id, project_id=project_id)
                .first()
            )
            return perm.role if perm else None
        finally:
            session.close()

    def get_accessible_projects(self, user_id: int) -> List[int]:
        """Список ID проектов, доступных пользователю."""
        session = SessionLocal()
        try:
            perms = session.query(ProjectPermission).filter_by(user_id=user_id).all()
            return [perm.project_id for perm in perms]
        finally:
            session.close()

    def can_manage_project(self, user_id: int, project_id: int) -> bool:
        """Проверка: может ли пользователь управлять проектом (project_admin)."""
        role = self.get_project_role(user_id, project_id)
        return role == "project_admin"


# Global instance
permission_service = PermissionService()
