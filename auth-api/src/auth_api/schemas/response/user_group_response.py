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
"""User group response schema"""
from marshmallow import Schema, fields


class UserGroupResponseSchema(Schema):
    """User group response schema"""

    id = fields.Str(metadata={"description": "Id of the group"})
    name = fields.Str(metadata={"description": "Name of the group"})
    path = fields.Method("get_path")

    level = fields.Method("get_level")
    display_name = fields.Method("get_display_name")

    def get_level(self, instance):
        """Get the level of the group, or return None if not present or invalid"""
        attributes = instance.get("attributes", {})
        level = attributes.get("level", [None])[0]
        return int(level) if level is not None and level.isdigit() else None

    def get_display_name(self, instance):
        """Get the display name of the group, or return None if not present"""
        attributes = instance.get("attributes", {})
        return attributes.get("display_name", [None])[0]

    def get_path(self, instance):
        """Format the path of the group from Keycloak, or return an empty string if not present"""
        path = instance.get("path", "")
        return path[1:] if path else ""