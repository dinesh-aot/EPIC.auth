# Copyright © 2019 Province of British Columbia
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Keycloak admin functions."""
from urllib.parse import urlencode

import requests
from flask import current_app

from auth_api.utils.enums import HttpMethod


class KeycloakService:
    """Keycloak services."""

    @staticmethod
    def get_groups(brief_representation: bool = False):
        """Get all the groups."""
        response = KeycloakService._request_keycloak(
            f"groups?briefRepresentation={brief_representation}"
        )
        return response.json()

    @staticmethod
    def get_user():
        """Get users."""
        response = KeycloakService._request_keycloak("users?max=2000")
        return response.json()

    @classmethod
    def get_user_groups_by_id(cls, user_id):
        """Get groups of a specific user by their ID."""
        response = KeycloakService._request_keycloak(f"users/{user_id}/groups")
        return response.json()

    @staticmethod
    def get_user_by_username(username):
        """Get users."""
        response = KeycloakService._request_keycloak(f"users?username={username}")
        users = response.json()

        if not users:
            raise ValueError(f"User with username '{username}' not found.")

        # Assuming usernames are unique, return the first user found
        return users[0]

    @staticmethod
    def dangerously_overwrite_all_user_data(user_id: str, user_representation: dict):
        """Update an existing Keycloak user.

        ⚠️ WARNING:
        This method performs a FULL REPLACEMENT of the UserRepresentation object in Keycloak.
        Any fields not included in `user_representation` will be OVERWRITTEN or CLEARED.

        Always perform a GET request first to fetch the existing user,
        apply only the changes you need, and then PUT the complete representation back.
        Never send partial data directly to this endpoint — Keycloak does not perform merging.

        :param user_id: The Keycloak user UUID.
        :param user_representation: The full UserRepresentation JSON to PUT.
        :return: The raw response from Keycloak (204 No Content expected on success).
        """
        import json

        # ⚠️ CRITICAL NOTE:
        # This call sends the entire user object as-is.
        # If `user_representation` is missing fields (e.g., attributes, federatedIdentities),
        # Keycloak will interpret them as removed and wipe them out.
        #
        # Safe pattern:
        #   1. user = get_user_by_id(user_id)
        #   2. modify user fields as needed
        #   3. update_user(user_id, user)
        #
        # This ensures you preserve all other properties.
        response = KeycloakService._request_keycloak(
            f"users/{user_id}",
            HttpMethod.PUT,
            data=json.dumps(user_representation)
        )

        return response

    @staticmethod
    def get_user_by_id(user_id):
        """Get users."""
        response = KeycloakService._request_keycloak(f"users/{user_id}")
        user = response.json()

        if not user:
            raise ValueError(f"User not found.")

        # Assuming usernames are unique, return the first user found
        return user

    @staticmethod
    def get_users(search_text: str = None):
        """Return a list of users from Keycloak, optionally filtered by search term."""
        max_users = 2000
        query_params = {'max': max_users}

        if search_text:
            query_params['search'] = search_text

        query_string = urlencode(query_params)
        endpoint = f"users?{query_string}"

        response = KeycloakService._request_keycloak(endpoint)
        return response.json()

    @staticmethod
    def get_members_for_groups(groups):
        """Get all groups with their members."""
        # For each group, get its members
        for group in groups:
            group_id = group["id"]
            members_response = KeycloakService._request_keycloak(
                f"groups/{group_id}/members"
            )
            group["members"] = members_response.json()

        return groups

    @staticmethod
    def get_group_members(group_id):
        """Get the members of a group."""
        response = KeycloakService._request_keycloak(f"groups/{group_id}/members")
        return response.json()

    @staticmethod
    def get_group_id_by_name(group_name):
        """Get the group ID by its name."""
        groups = KeycloakService.get_groups(brief_representation=True)
        for group in groups:
            if group["name"] == group_name:
                return group["id"]
        raise ValueError(f"Group with name '{group_name}' not found.")

    @staticmethod
    def update_user_group(user_id, group_id):
        """Update the group of user."""
        kc_user_id = KeycloakService.get_user_by_username(user_id)["id"]
        return KeycloakService._request_keycloak(
            f"users/{kc_user_id}/groups/{group_id}", HttpMethod.PUT
        )

    @staticmethod
    def delete_user_group(user_id, group_id, kc_user_id=None):
        """Delete user-group mapping."""
        if not kc_user_id:
            kc_user_id = KeycloakService.get_user_by_username(user_id)["id"]
        return KeycloakService._request_keycloak(
            f"users/{kc_user_id}/groups/{group_id}", HttpMethod.DELETE
        )

    @staticmethod
    def _request_keycloak(
        relative_url, http_method: HttpMethod = HttpMethod.GET, data=None
    ):
        """Request actual keycloak service."""
        config = current_app.config
        base_url = config.get("KEYCLOAK_BASE_URL")
        realm = config.get("KEYCLOAK_REALM_NAME")
        timeout = int(config.get("CONNECT_TIMEOUT", 60))
        admin_token = KeycloakService._get_admin_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}",
        }

        url = f"{base_url}/auth/admin/realms/{realm}/{relative_url}"
        if http_method == HttpMethod.GET:
            response = requests.get(url, headers=headers, timeout=timeout)
        if http_method == HttpMethod.PUT:
            response = requests.put(url, headers=headers, data=data, timeout=timeout)
        if http_method == HttpMethod.DELETE:
            response = requests.delete(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response

    @staticmethod
    def get_user_groups_by_username(username, user_id=None, brief_representation=False):
        """Get groups directly associated with a specific user by their ID."""
        if not user_id:
            user_id = KeycloakService.get_user_by_username(username)["id"]
        response = KeycloakService._request_keycloak(f"users/{user_id}/groups?briefRepresentation={brief_representation}")
        return response.json()

    @staticmethod
    def get_sub_groups(group_id):
        """Return the subgroups of given group."""
        response = KeycloakService._request_keycloak(f"groups/{group_id}/children")
        return response.json()

    @staticmethod
    def _get_admin_token():
        """Create an admin token."""
        config = current_app.config
        base_url = config.get("KEYCLOAK_BASE_URL")
        realm = config.get("KEYCLOAK_REALM_NAME")
        admin_client_id = config.get("KEYCLOAK_ADMIN_CLIENT")
        admin_secret = config.get("KEYCLOAK_ADMIN_SECRET")
        timeout = int(config.get("CONNECT_TIMEOUT", 60))
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        token_url = f"{base_url}/auth/realms/{realm}/protocol/openid-connect/token"

        response = requests.post(
            token_url,
            data=f"client_id={admin_client_id}&grant_type=client_credentials"
            f"&client_secret={admin_secret}",
            headers=headers,
            timeout=timeout,
        )
        return response.json().get("access_token")

    @staticmethod
    def get_group_by_name(group_name, sub_group_name=None):
        """Get group by its name."""
        request_url = "groups"
        if sub_group_name:
            request_url += f"?search={sub_group_name}"
        response = KeycloakService._request_keycloak(request_url)
        groups = response.json()
        for group in groups:
            if group["name"] == group_name:
                return group
        raise ValueError(f"Group with name '{group_name}' not found.")

    @staticmethod
    def get_user_by_email(email: str):
        """Get a Keycloak user by email address."""
        response = KeycloakService._request_keycloak(f"users?email={email}")
        users = response.json()

        if not users:
            raise ValueError(f"User with email '{email}' not found.")

        return users[0]
