# Copyright © 2024 Province of British Columbia
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
"""API endpoints for managing an user resource."""

from http import HTTPStatus

from flask import request
from flask_restx import Namespace, Resource

from auth_api.auth import auth
from auth_api.exceptions import BusinessError, ResourceNotFoundError
from auth_api.schemas.response.user_response import UserResponseSchema
from auth_api.schemas.response.user_group_response import UserGroupResponseSchema
from auth_api.schemas.request.get_group_members import GetGroupByNameRequest
from auth_api.schemas.user import UserSchema, UserUpdateRequestSchema
from auth_api.services.user_service import UserService
from auth_api.utils.util import cors_preflight

from .apihelper import Api as ApiHelper

API = Namespace("users", description="Endpoints for User Management")
"""Custom exception messages
"""

user_partial_update_model = ApiHelper.convert_ma_schema_to_restx_model(
    API, UserUpdateRequestSchema(), "User Update Request Model"
)
user_list_model = ApiHelper.convert_ma_schema_to_restx_model(
    API, UserSchema(), "UserListItem"
)
group_list_model = ApiHelper.convert_ma_schema_to_restx_model(
    API, UserGroupResponseSchema(), "UserListItem"
)
user_response_list_model = ApiHelper.convert_ma_schema_to_restx_model(
    API, UserResponseSchema(), "UserResponseList"
)


@cors_preflight("GET, OPTIONS, POST")
@API.route("", methods=["POST", "GET", "OPTIONS"])
class Users(Resource):
    """Resource for managing users."""

    @staticmethod
    @API.response(code=200, description="Success", model=[user_list_model])
    @ApiHelper.swagger_decorators(API, endpoint_description="Fetch all users")
    @API.response(400, "Bad Request")
    @API.response(404, "Not Found")
    @auth.require
    def get():
        """Fetch all users."""
        include_groups = request.args.get("include_groups", "true").lower() == "true"
        search_text = request.args.get("search", None)
        users = UserService.get_all_users(include_groups=include_groups, search_text=search_text)
        user_list_schema = UserSchema(many=True)
        return user_list_schema.dump(users), HTTPStatus.OK


@cors_preflight("GET, OPTIONS, PATCH, DELETE")
@API.route("/<username>", methods=["PATCH", "GET", "OPTIONS", "DELETE"])
@API.doc(params={"username": "The user identifier"})
class User(Resource):
    """Resource for managing a single user."""

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(API, endpoint_description="Fetch a user by id")
    @API.response(code=200, model=user_list_model, description="Success")
    @API.response(404, "Not Found")
    def get(username):
        """Fetch a user by username."""
        group_brief_representation = request.args.get("group_brief_representation", "false").lower() == "true"
        user = UserService.get_user_by_username(username, group_brief_representation)
        if not user:
            raise ResourceNotFoundError(f"User with {username} not found")
        return UserSchema().dump(user), HTTPStatus.OK

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(API, endpoint_description="Update allowed fields of a user (partial)")
    @API.expect(user_partial_update_model)
    @API.response(code=200, model=user_list_model, description="Success")
    @API.response(400, "Bad Request")
    @API.response(404, "Not Found")
    def patch(username):
        """Update a user by username."""
        user_data = UserUpdateRequestSchema().load(API.payload)
        UserService.update_user_by_username(username, user_data)
        return None, HTTPStatus.NO_CONTENT


@cors_preflight("GET, OPTIONS, PATCH, DELETE")
@API.route("/guid/<user_auth_guid>", methods=["PATCH", "GET", "OPTIONS", "DELETE"])
@API.doc(params={"username": "The user identifier"})
class UserById(Resource):
    """Resource for managing a single user."""

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(API, endpoint_description="Fetch a user by id")
    @API.response(code=200, model=user_list_model, description="Success")
    @API.response(404, "Not Found")
    def get(user_auth_guid):
        """Fetch a user by username."""
        group_brief_representation = request.args.get("group_brief_representation", "false").lower() == "true"
        user = UserService.get_user_by_id(user_auth_guid, group_brief_representation)
        if not user:
            raise ResourceNotFoundError(f"User {user_auth_guid} not found")
        return UserSchema().dump(user), HTTPStatus.OK


@cors_preflight("GET, OPTIONS, PUT, DELETE")
@API.route("/<user_id>/groups", methods=["GET", "OPTIONS", "PUT", "DELETE"])
@API.doc(params={"user_id": "The user identifier"})
class UserGroups(Resource):
    """Resource for managing user groups."""

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(API, endpoint_description="Fetch groups by user id")
    @API.response(404, "Not Found")
    def get(user_id):
        """Fetch groups for a user by id."""
        groups = UserService.get_groups_by_username(user_id)
        if not groups:
            raise ResourceNotFoundError(f"No groups found for user with {user_id}")
        return UserGroupResponseSchema(many=True).dump(groups), HTTPStatus.OK

    @staticmethod
    @auth.require
    def put(user_id):
        """Update the group of the user."""
        response = UserService.update_user_group(user_id, API.payload)
        if response.status_code == 204:
            return "", HTTPStatus.NO_CONTENT
        raise BusinessError("Update failed", 500)

    @staticmethod
    @auth.require
    def delete(user_id):
        """Delete group mapping of the user."""
        success = UserService.delete_all_user_groups(user_id)
        if success:
            return "", HTTPStatus.NO_CONTENT
        return "", HTTPStatus.INTERNAL_SERVER_ERROR


@cors_preflight("OPTIONS, PUT, DELETE")
@API.route("/<user_id>/groups/<string:group_name>", methods=["OPTIONS", "PUT", "DELETE"])
@API.doc(params={"user_id": "The user identifier", "group_name": "Name of the group"})
@API.doc(
    params={
        "del_sub_group_mappings": {
            "description": "Delete all the sub group mappings of the given parent group",
            "type": "boolean",
            "required": False,
        }
    }
)
class UserGroupName(Resource):
    """Resource to manage UserGroup by name."""

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(
        API, endpoint_description="Assign user to a specific group by name"
    )
    @API.response(204, "No Content")
    @API.response(404, "Not Found")
    def put(user_id, group_name):
        """Assign user to a group by name, with optional sub_group_name."""
        sub_group_name = request.args.get("sub_group_name", None)
        try:
            response = UserService.assign_user_to_named_group(
                user_id, group_name, sub_group_name
            )
        except ValueError as e:
            raise ResourceNotFoundError(str(e))
        if response.status_code == 204:
            return "", HTTPStatus.NO_CONTENT
        raise BusinessError("Group assignment failed", 500)

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(
        API, endpoint_description="Delete the user-group mapping"
    )
    @API.response(404, "Not Found")
    @API.response(204, "No Content")
    def delete(user_id, group_name):
        """Delete the user group mapping by the group name."""
        del_sub_group_mappings = bool(request.args.get("del_sub_group_mappings", False))
        payload = API.payload
        UserService.delete_user_group(user_id, group_name, del_sub_group_mappings, payload)
        return {}, HTTPStatus.NO_CONTENT


@cors_preflight("GET, ""OPTIONS")
@API.route("/groups/<group_name>/members", methods=["GET", "OPTIONS"])
class GroupMembers(Resource):
    """Group resource."""

    @staticmethod
    @ApiHelper.swagger_decorators(
        API, endpoint_description="Fetch all members of a group"
    )
    @API.response(code=200, model=user_response_list_model, description="Group Members List")
    @API.response(404, "Not Found")
    @auth.require
    def get(group_name):
        """Get group members by name."""
        sub_group_name = request.args.get("sub_group_name", None)
        group_data = GetGroupByNameRequest().load(
            {"group_name": group_name, "sub_group_name": sub_group_name}
        )
        response_schema = UserResponseSchema(many=True)
        members = UserService.get_group_members(group_data)
        return response_schema.dump(members), HTTPStatus.OK


@cors_preflight("GET, OPTIONS")
@API.route("/email/<string:email>", methods=["GET", "OPTIONS"])
@API.doc(params={"email": "The email address of the user"})
class UserByEmail(Resource):
    """Resource for fetching a user by email."""

    @staticmethod
    @auth.require
    @ApiHelper.swagger_decorators(
        API, endpoint_description="Fetch a user by email address"
    )
    @API.response(code=200, model=user_list_model, description="Success")
    @API.response(404, "Not Found")
    def get(email):
        """Fetch a user by email address."""
        try:
            user = UserService.get_user_by_email(email)
        except ValueError:
            raise ResourceNotFoundError(
                f"User with email '{email}' not found"
            )
        if not user:
            raise ResourceNotFoundError(
                f"User with email '{email}' not found"
            )
        return UserSchema().dump(user), HTTPStatus.OK
