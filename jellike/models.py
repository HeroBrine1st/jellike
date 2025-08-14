from typing import Literal, Annotated
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, PlainSerializer

class WebhookRequestBody(BaseModel):
    """
    {{#if_equals SaveReason "UpdateUserRating"}}
    {
        "item_id": "{{ItemId}}",
        "is_favourite": {{#if Favorite}}true{{else}}false{{/if}},
        "user_id": "{{UserId}}"
    }
    {{/if_equals}}
    """
    item_id: UUID
    user_id: UUID
    is_favourite: bool

class PersistentState(BaseModel):
    playlist_by_user: dict[UUID, UUID] = Field(default_factory=dict)

# https://api.jellyfin.org/#tag/Playlists/operation/CreatePlaylist
# POST /Playlists
class CreatePlaylistRequestBody(BaseModel):
    class User(BaseModel):
        id: Annotated[UUID, PlainSerializer(lambda x: x.hex)] = Field(serialization_alias="UserId")
        can_edit: bool = Field(serialization_alias="CanEdit")

        # THIS wasted another 15 minutes! It needs in both models!
        # Furthermore, jellyfin does not reject such request!
        model_config = ConfigDict(serialize_by_alias=True)

    name: str = Field(serialization_alias="Name")
    item_ids: list[UUID] = Field(serialization_alias="Ids")
    creator_user_id: UUID = Field(serialization_alias="UserId")
    media_type: Literal["Audio"] = Field(default="Audio", serialization_alias="MediaType")
    users: list[User] = Field(default_factory=list, serialization_alias="Users")
    public: bool = Field(default=False, serialization_alias="IsPublic")

    # https://docs.pydantic.dev/latest/concepts/alias/#serialization
    # Thank you, I lost 30 minutes! Added up to whole 3 hours of debugging!
    # I did all the code myself, why am I trying to start it like it is vibecoded?
    model_config = ConfigDict(serialize_by_alias=True)
