"""Service for user management."""

from flask import g, current_app

from auth_api.exceptions import ResourceNotFoundError, UnprocessableEntityError
from auth_api.models.user import User as UserModel

from .keycloak import KeycloakService
from ..utils.util import get_current_app

ALLOWED_USER_UPDATE_FIELDS = {
    "firstName",
    "lastName",
    "enabled",
}


class UserService:
    """User management service."""

    @classmethod
    def get_user_by_id(cls, user_id, group_brief_representation=False):
        """Get user by username."""
        app_name = g.app_name
        user = KeycloakService.get_user_by_id(user_id)
        username = user.get("username")
        enriched_user = cls.enrich_user_with_groups(app_name, group_brief_representation, user, user_id, username)
        return enriched_user

    @classmethod
    def get_user_by_username(cls, username, group_brief_representation=False):
        """Get user by username."""
        app_name = g.app_name
        user = KeycloakService.get_user_by_username(username)
        user_id = user.get("id")
        enriched_user = cls.enrich_user_with_groups(app_name, group_brief_representation, user, user_id, username)
        return enriched_user

    @classmethod
    def _validate_user_update_allowed_fields(cls, user_data: dict):
        """Ensure only allowed fields are being updated."""
        invalid_fields = [key for key in user_data if key not in ALLOWED_USER_UPDATE_FIELDS]
        if invalid_fields:
            raise ValueError(f"Update contains disallowed fields: {invalid_fields}")

    @classmethod
    def update_user_by_username(cls, username, user_data):
        """Update a Keycloak user by username with strict field control.

        Only a limited set of safe fields are updatable. All other fields are preserved.

        :param username: The Keycloak username.
        :param user_data: Partial UserRepresentation with only allowed fields.
        :return: The updated user representation.
        """
        cls._validate_user_update_allowed_fields(user_data)

        # ⚠️ IMPORTANT: Keycloak's PUT /users/{id} endpoint does NOT merge data.
        # It expects the FULL UserRepresentation and will REPLACE missing fields with null/empty values.
        # So we must fetch the existing user first to preserve all unchanged data.
        user = KeycloakService.get_user_by_username(username)
        user_id = user.get("id")

        if not user_id:
            raise ValueError(f"User '{username}' not found in Keycloak.")

        for key, value in user_data.items():
            user[key] = value

        response = KeycloakService.dangerously_overwrite_all_user_data(user_id, user)
        response.raise_for_status()
        return

    @classmethod
    def enrich_user_with_groups(cls, app_name, group_brief_representation, user, user_id, username):
        user_groups = KeycloakService.get_user_groups_by_username(username, user_id, group_brief_representation)
        app_groups = (
            [
                group
                for group in user_groups
                if app_name.lower() in group.get("path", "").lower()
            ]
            if app_name
            else user_groups
        )
        # Add groups to user data
        user["groups"] = app_groups
        return user

    @classmethod
    def get_all_users(cls, include_groups: bool = True, search_text: str = None):
        """Get all users, optionally filtered by app name and with optional group mapping."""
        users = KeycloakService.get_users(search_text)
        if not include_groups:
            return users

        app_name = g.get("app_name", None)
        groups = cls._get_relevant_groups(app_name)

        group_members_map = cls._map_group_members(groups)

        cls._assign_groups_to_users(users, groups, group_members_map)

        return cls._filter_users_by_group(users) if app_name else users

    @classmethod
    def _get_relevant_groups(cls, app_name: str):
        """Return sorted groups, optionally filtered by app name."""
        all_groups = cls.get_groups()
        if app_name:
            return sorted(
                [group for group in all_groups if app_name.lower() in group.get("path", "").lower()],
                key=cls._get_level
            )
        return sorted(all_groups, key=cls._get_level)

    @classmethod
    def _map_group_members(cls, groups):
        """Return a mapping of group_id to set of user_ids."""
        group_members = {}
        for group in groups:
            members = KeycloakService.get_group_members(group["id"])
            group_members[group["id"]] = {m["id"] for m in members}
        return group_members

    @classmethod
    def _assign_groups_to_users(cls, users, groups, group_members_map):
        """Mutate user objects by adding their group memberships."""
        for user in users:
            user["groups"] = [
                group
                for group in groups
                if user["id"] in group_members_map.get(group["id"], set())
            ]

    @classmethod
    def _filter_users_by_group(cls, users):
        """Return only users who belong to at least one group."""
        return [user for user in users if user["groups"]]

    @classmethod
    def _get_level(cls, group):
        """Get the level from the group, defaulting to 0 if not valid."""
        # Safely retrieve the level attribute and default to 0 if not valid
        level_str = group.get("attributes", {}).get("level", [0])[0]
        try:
            return int(level_str)
        except (ValueError, TypeError):
            return 0

    @classmethod
    def update_user_group(cls, user_id, user_data):
        """Update users group."""
        app_name = g.app_name or user_data.get("app_name")
        group_name = user_data.get("group_name")

        path = f"/{app_name}/{group_name}" if app_name else group_name
        all_groups = cls.get_groups()
        parent_group = next(
            (group for group in all_groups if group["name"] == app_name), None
        )
        group = next(
            (
                group
                for group in all_groups
                if group["name"] == group_name and group["path"] == path
            ),
            None,
        )
        result = KeycloakService.update_user_group(user_id, group["id"])
        all_groups_except_new_group = [
            cgroup
            for cgroup in all_groups
            if "parentId" in cgroup
               and cgroup["parentId"] == parent_group["id"]
               and cgroup["id"] != group["id"]
        ]
        if len(all_groups_except_new_group) > 0:
            for del_group in all_groups_except_new_group:
                KeycloakService.delete_user_group(user_id, del_group["id"])
        return result

    @classmethod
    def delete_user_group(cls, user_id, group_name, del_sub_group_mappings, user_data=None):
        """Delete the user-group mapping in keycloak."""
        app_name = g.app_name or (user_data.get("app_name") if user_data else None)
        if app_name == group_name:
            path = f"/{app_name}"
        else:
            path = f"/{app_name}/{group_name}" if app_name else group_name
        all_groups = cls.get_groups()
        group = next(
            (
                group
                for group in all_groups
                if group["name"] == group_name and group["path"] == path
            ),
            None,
        )
        if not group:
            raise ResourceNotFoundError("Group doesn't exist with the given name")
        if group.get("subGroupCount", 0) > 0:
            if del_sub_group_mappings is False:
                raise UnprocessableEntityError(
                    "The requested action will delete all the subgroup mappings of the"
                    "given parent. Please pass 'del_sub_group_mappings' as 'true' if you want to proceed."
                )
            mapped_groups = cls.get_groups_by_username(username=user_id)
            mapped_sub_groups = [
                mapped
                for mapped in mapped_groups
                if mapped.get("parentId", None) == group["id"]
            ]
            for mapped in mapped_sub_groups:
                KeycloakService.delete_user_group(user_id, mapped["id"])
        else:
            KeycloakService.delete_user_group(user_id, group["id"])

    @classmethod
    def delete_all_user_groups(cls, user_id):
        """Delete all user-group mappings for a user."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        mapped_groups = cls.get_groups_by_username(user_id)
        results = []
        kc_user_id = KeycloakService.get_user_by_username(user_id)["id"]

        app = get_current_app()

        def delete_from_keycloak(group):
            with app.app_context():
                try:
                    response = KeycloakService.delete_user_group(user_id, group["id"], kc_user_id=kc_user_id)
                    return response.status_code == 204
                except Exception as e:
                    current_app.logger.error(
                        f"Failed to delete group {group['id']} for user {user_id}: {e}"
                    )
                    return False

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(delete_from_keycloak, group) for group in mapped_groups]
            for future in as_completed(futures):
                results.append(future.result())

        return all(results)

    @classmethod
    def get_groups(cls):
        """Get groups that has "level" attribute set up."""
        groups = KeycloakService.get_groups()
        all_groups = []

        for group in groups:
            all_groups.append(group)
            if group.get("subGroupCount", 0) > 0:
                sub_groups = KeycloakService.get_sub_groups(group["id"])
                all_groups.extend(sub_groups)

        return all_groups

    @classmethod
    def get_user_by_email(cls, email: str):
        """Get user by email address, enriched with groups."""
        app_name = g.app_name
        user = KeycloakService.get_user_by_email(email)
        user_id = user.get("id")
        username = user.get("username")
        enriched_user = cls.enrich_user_with_groups(
            app_name, False, user, user_id, username
        )
        return enriched_user

    @classmethod
    def assign_user_to_named_group(cls, username, group_name, sub_group_name=None):
        """Assign a user to a group by name, optionally targeting a sub-group.

        :param username: The Keycloak username of the user.
        :param group_name: The name of the parent group.
        :param sub_group_name: Optional sub-group name within the parent.
        :return: The response from the Keycloak group assignment.
        :raises ValueError: If group or sub-group is not found.
        """
        all_groups = cls.get_groups()

        if sub_group_name:
            parent_group = next(
                (grp for grp in all_groups if grp["name"] == group_name),
                None,
            )
            if not parent_group:
                raise ValueError(
                    f"Parent group '{group_name}' not found."
                )
            sub_groups = KeycloakService.get_sub_groups(parent_group["id"])
            target_group = next(
                (sg for sg in sub_groups if sg["name"] == sub_group_name),
                None,
            )
            if not target_group:
                raise ValueError(
                    f"Sub-group '{sub_group_name}' not found "
                    f"under '{group_name}'."
                )
        else:
            target_group = next(
                (grp for grp in all_groups if grp["name"] == group_name),
                None,
            )
            if not target_group:
                raise ValueError(
                    f"Group '{group_name}' not found."
                )

        return KeycloakService.update_user_group(username, target_group["id"])

    @classmethod
    def get_groups_by_username(cls, username):
        """Get groups for a specific user by their ID."""
        groups = KeycloakService.get_user_groups_by_username(username)
        return groups

    @classmethod
    def get_group_members(cls, group_data):
        """Get the members of a group by its name."""
        current_app.logger.debug("Fetching group members with data: %s", group_data)
        group_name = group_data.get("group_name")
        sub_group_name = group_data.get("sub_group_name")

        current_app.logger.debug("Fetching group by name: %s, sub-group: %s", group_name, sub_group_name)
        group = KeycloakService.get_group_by_name(group_name, sub_group_name)

        if not group:
            current_app.logger.error("Group with name '%s' not found.", group_name)
            raise ResourceNotFoundError(f"Group with name '{group_name}' not found.")

        if sub_group_name:
            current_app.logger.debug("Searching for sub-group: %s in group: %s", sub_group_name, group_name)
            group = next(
                (
                    sub_group
                    for sub_group in group.get('subGroups', [])
                    if sub_group.get("name") == sub_group_name
                ),
                None,
            )
            if not group:
                current_app.logger.error(
                    "Sub-group with name '%s' not found in group '%s'.", sub_group_name, group_name
                )
                raise ResourceNotFoundError(
                    f"Sub-group with name '{sub_group_name}' not found in group '{group_name}'."
                )

        group_id = group.get("id")
        if not group_id:
            current_app.logger.error("Group ID is missing or invalid for group: %s", group_name)
            raise UnprocessableEntityError("Group ID is missing or invalid.")

        current_app.logger.debug("Fetching members for group ID: %s", group_id)
        members = KeycloakService.get_group_members(group_id)
        current_app.logger.debug("Fetched %d members for group ID: %s", len(members), group_id)
        return members
