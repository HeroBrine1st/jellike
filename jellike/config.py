from typing import Literal, Any, Annotated
from uuid import UUID

from pydantic import Field, DirectoryPath, HttpUrl, WrapValidator
from pydantic_settings import BaseSettings, NoDecode

def str_to_dict(v: Any, handler) -> Any:
    if isinstance(v, str):
        # "KEY=VALUE:KEY=VALUE"
        return handler(dict(item.split("=", 1) for item in v.split(":")))
    else:
        return handler(v)

class Config(BaseSettings):
    user_id: UUID = Field(default=..., description="An author of playlists created by the service")
    user_token: str = Field(
        default=...,
        description="A token used to access Jellyfin server. "
                    "Should be user-scoped (use get_user_token.py) to avoid https://github.com/jellyfin/jellyfin/issues/12999",
    )
    api_token: str = Field(
        default=...,
        description="A token used to access Jellyfin server. "
                    "Should be global (Dashboard -> API Keys) to access user favourites",
    )
    jellyfin_url: HttpUrl = Field(default=...)
    # noinspection PyTypeHints
    data_dir: DirectoryPath = Field(default=..., description="Path to persistent directory state")
    base_playlists: Annotated[dict[UUID, UUID], WrapValidator(str_to_dict), NoDecode] = Field(
        description="A map from user id to base playlist. Tracks from base playlist are considered liked. "
                    "The playlist is assumed immutable, otherwise behavior is undefined. "
                    "It is recommended to use it for initial migration, then like all items and remove from config for increased performance. "
                    "Adding or removing this setting after jellike created the playlist has no effect, it is only used on playlist creation. "
                    "Format is USER_ID=PLAYLIST_ID:USER_ID=PLAYLIST_ID for environment variable.",
        default_factory=dict,
    )
    order: Literal["forward", "reverse"] = Field(
        description="Forward order adds tracks to the end of the playlist (the default), reverse order adds tracks to the start of the playlist. "
                    "Applying PR https://github.com/jellyfin/jellyfin/pull/13730 is required for \"reverse\" (first included in Jellyfin 10.11-RC1)",
        default="forward",
    )
    delay_before_upload_playlist_image_seconds: int = Field(
        default=5,
        description="Jellyfin creates playlist image itself. "
                    "If jellike uploads playlist image too early, it will be overriden by jellyfin.",
    )
