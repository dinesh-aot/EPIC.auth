# Copyright © 2024 Province of British Columbia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Local fixtures for resource-level unit tests.

These tests build a lightweight Flask app per test and mock the service layer,
so the Docker-backed Keycloak setup from the top-level conftest is not needed.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def auto():  # pylint: disable=function-redefined
    """Override the Docker-backed session fixture with a no-op for resource tests."""
    yield
