# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unified image-gallery query tool."""

from plugin.framework.tool_base import ToolBase
from plugin.framework.tool_merge import merged_parameters, dispatch
from plugin.modules.images.tools.list_images import ListImages
from plugin.modules.images.tools.search_images import SearchImages
from plugin.modules.images.tools.get_image_info import GetImageInfo


class GalleryQuery(ToolBase):
    """Browse, search or inspect images in the configured galleries."""

    _IMPL = {
        "list": ListImages,
        "search": SearchImages,
        "get": GetImageInfo,
    }

    name = "gallery_query"
    aliases = {
        "gallery_list": {"action": "list"},
        "gallery_search": {"action": "search"},
        "gallery_get": {"action": "get"},
    }
    intent = "media"
    description = (
        "Query the image galleries: action='list' browses them, "
        "action='search' matches a query, action='get' returns the "
        "detail of one image."
    )
    parameters = merged_parameters(
        _IMPL, "Browse, search, or fetch one image (default: list).")
    requires_service = "images"
    is_mutation = False

    def execute(self, ctx, **kwargs):
        action = kwargs.pop("action", "list")
        return dispatch(self._IMPL, ctx, action, kwargs)
