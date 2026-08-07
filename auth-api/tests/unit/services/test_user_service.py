"""Tests for UserService new methods (get_user_by_email, assign_user_to_named_group)."""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from auth_api.services.user_service import UserService


@pytest.fixture()
def app():
    """Create a minimal Flask app for testing."""
    _app = Flask(__name__)
    _app.config["TESTING"] = True
    return _app


class TestGetUserByEmail:
    """Tests for UserService.get_user_by_email."""

    @patch("auth_api.services.user_service.KeycloakService")
    def test_get_user_by_email_success(self, mock_kc, app):
        """Test successful email lookup returns enriched user."""
        with app.app_context():
            g.app_name = "SUBMIT"

            mock_user = {
                "id": "kc-uuid-123",
                "username": "testuser",
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@gov.bc.ca",
            }
            mock_kc.get_user_by_email.return_value = mock_user
            mock_kc.get_user_groups_by_username.return_value = [
                {"id": "g1", "name": "SUBMIT", "path": "/SUBMIT"}
            ]

            result = UserService.get_user_by_email("john@gov.bc.ca")

            mock_kc.get_user_by_email.assert_called_once_with("john@gov.bc.ca")
            assert result["username"] == "testuser"
            assert result["email"] == "john@gov.bc.ca"
            assert "groups" in result

    @patch("auth_api.services.user_service.KeycloakService")
    def test_get_user_by_email_not_found(self, mock_kc, app):
        """Test email lookup raises ValueError when user not found."""
        with app.app_context():
            g.app_name = "SUBMIT"

            mock_kc.get_user_by_email.side_effect = ValueError(
                "User with email 'nobody@gov.bc.ca' not found."
            )

            with pytest.raises(ValueError):
                UserService.get_user_by_email("nobody@gov.bc.ca")


class TestAssignUserToNamedGroup:
    """Tests for UserService.assign_user_to_named_group."""

    @patch("auth_api.services.user_service.KeycloakService")
    def test_assign_user_to_group_without_subgroup(self, mock_kc, app):
        """Test assigning user to a top-level group."""
        with app.app_context():
            g.app_name = "SUBMIT"

            mock_kc.get_groups.return_value = [
                {"id": "g1", "name": "SUBMIT", "path": "/SUBMIT", "subGroupCount": 0}
            ]
            mock_kc.get_sub_groups.return_value = []
            mock_kc.update_user_group.return_value = MagicMock(status_code=204)

            result = UserService.assign_user_to_named_group("testuser", "SUBMIT")

            mock_kc.update_user_group.assert_called_once_with("testuser", "g1")
            assert result.status_code == 204

    @patch("auth_api.services.user_service.KeycloakService")
    def test_assign_user_to_subgroup(self, mock_kc, app):
        """Test assigning user to a sub-group."""
        with app.app_context():
            g.app_name = "SUBMIT"

            mock_kc.get_groups.return_value = [
                {"id": "g1", "name": "SUBMIT", "path": "/SUBMIT", "subGroupCount": 1}
            ]
            mock_kc.get_sub_groups.return_value = [
                {"id": "sg1", "name": "EAO_MANAGER", "path": "/SUBMIT/EAO_MANAGER"}
            ]
            mock_kc.update_user_group.return_value = MagicMock(status_code=204)

            result = UserService.assign_user_to_named_group(
                "testuser", "SUBMIT", "EAO_MANAGER"
            )

            mock_kc.update_user_group.assert_called_once_with("testuser", "sg1")
            assert result.status_code == 204

    @patch("auth_api.services.user_service.KeycloakService")
    def test_assign_user_to_nonexistent_group(self, mock_kc, app):
        """Test assigning user to a group that doesn't exist raises error."""
        with app.app_context():
            g.app_name = "SUBMIT"

            mock_kc.get_groups.return_value = [
                {"id": "g1", "name": "SUBMIT", "path": "/SUBMIT", "subGroupCount": 0}
            ]
            mock_kc.get_sub_groups.return_value = []

            with pytest.raises(ValueError, match="not found"):
                UserService.assign_user_to_named_group(
                    "testuser", "NONEXISTENT"
                )
