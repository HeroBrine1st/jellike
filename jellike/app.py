import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Awaitable
from uuid import UUID

from aiofile import async_open, TextFileWrapper
from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response
from httpx import AsyncClient
from starlette.responses import JSONResponse

from jellike.config import Config
from jellike.models import WebhookRequestBody, PersistentState, CreatePlaylistRequestBody
from jellike.scoped_lock import ScopedLock
from jellike.utils import HeaderFormatter

config = Config()
# update state only if flushed immediately, there's no ACID and application relies on unhealthy trait in case of failures
state: PersistentState = None  # type: ignore
user_client: AsyncClient = None  # type: ignore
api_client: AsyncClient = None  # type: ignore
scheduler: AsyncIOScheduler = None  # type: ignore
scoped_lock = ScopedLock()
healthy = False
recovery_job: Job = None  # type: ignore

handler = logging.StreamHandler()
handler.setFormatter(HeaderFormatter("%(header)s %(message)s"))
logging.basicConfig(level=logging.WARNING, handlers=[handler])
logger = logging.getLogger("Jellike")
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(_: FastAPI):
    global api_client, user_client, state, recovery_job

    if (state_file := config.data_dir / "state.json").exists():
        async with async_open(state_file) as f:
            f: TextFileWrapper
            state = PersistentState.model_validate_json(await f.read())
    else:
        state = PersistentState()

    logger.debug(f"Loaded state: {state!r}")
    logger.debug(f"Base playlists: {config.base_playlists!r}")

    scheduler = AsyncIOScheduler()
    api_client = AsyncClient(
        base_url=str(config.jellyfin_url), headers={
            'Authorization': f"MediaBrowser Token=\"{config.api_token}\"",
        },
    )
    user_client = AsyncClient(
        base_url=str(config.jellyfin_url), headers={
            'Authorization': f'MediaBrowser Token="{config.user_token}", Client="stub", Version="stub", DeviceId="gPJu1AKwNAQmH9wFwwbWSD3pHBD1tveF", Device="stub"',
        },
    )
    recovery_job = scheduler.add_job(
        recovery, "interval", minutes=1, id="recovery_job",
    )  # reschedules itself to 1 hour if successful
    async with api_client, user_client:
        await recovery()
        scheduler.start()
        yield
    scheduler.shutdown()
    client = None
    state = None

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(body: WebhookRequestBody):
    async with await scoped_lock.on(body.user_id):
        had_playlist = True
        if body.user_id not in state.playlist_by_user:
            had_playlist = False
            await create_playlist(body.user_id)
        await handle_favourite_change(body.user_id, body.item_id, body.is_favourite, full_run=had_playlist)

@app.get("/health")
async def healthcheck():
    return JSONResponse(
        status_code=200 if healthy else 503,  # middleware will respond with 503 itself but anyway
        content=healthy,
    )

@app.middleware("http")
async def tainter(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
    global healthy
    if not healthy:
        return JSONResponse(
            status_code=503,
            content={"detail": "Application has suffered a malfunction and so disabled itself to prevent corruption"},
        )
    try:
        return await call_next(request)
    except:
        healthy = False
        recovery_job.reschedule("interval", minutes=1)
        raise

async def handle_favourite_change(user_id: UUID, item_id: UUID, is_favourite: bool, full_run: bool = True):
    # full run means "not only move", simply to avoid boolean negation
    playlist_id = state.playlist_by_user[user_id]

    logger.debug(f"Handling {is_favourite=} for item {item_id!r} (user {user_id!r}, playlist {playlist_id!r})")

    if user_id in config.base_playlists:
        if item_id in await get_playlist(config.base_playlists[user_id]):
            logger.info(
                f"Skipping favourite change for item {item_id} because {user_id} has base playlist with this track",
            )
            return

    if is_favourite:
        # idk why it needs user id
        if full_run:
            (await user_client.post(
                f"/Playlists/{playlist_id.hex}/Items?ids={item_id.hex}&userId={config.user_id}",
            )).raise_for_status()
        if config.order == "reverse":
            # This endpoint requires no dashes in UUIDs, otherwise fails with NullReferenceException (but this time it is 500, not 400)
            # Used `hex` everywhere just in case
            (await user_client.post(f"/Playlists/{playlist_id.hex}/Items/{item_id.hex}/Move/0")).raise_for_status()
    elif full_run:
        (await user_client.delete(f"/Playlists/{playlist_id.hex}/Items?EntryIds={item_id.hex}")).raise_for_status()

# Assumes user_id is locked!
async def create_playlist(user_id: UUID):
    favourite_tracks = await get_user_favourite_tracks(user_id)

    resp = await user_client.post(
        "/Playlists",
        json=CreatePlaylistRequestBody(
            name="Liked songs",
            item_ids=favourite_tracks,
            creator_user_id=config.user_id,
            users=[
                CreatePlaylistRequestBody.User(
                    id=user_id,
                    can_edit=False,
                ),
            ],
        ).model_dump(mode="json"),
    )
    resp.raise_for_status()

    playlist_id: UUID = UUID(resp.json()["Id"])

    state.playlist_by_user[user_id] = playlist_id
    await flush_state()

    await asyncio.sleep(config.delay_before_upload_playlist_image_seconds)  # Otherwise jellyfin replaces image

    resp = await api_client.post(
        f"/Items/{playlist_id.hex}/Images/Primary",
        content=stream_logo(),
        headers={"Content-Type": "image/png"},
    )
    resp.raise_for_status()

async def stream_logo():
    # Jellyfin encodes images with base64!
    remainder = b''
    async with async_open(Path(__file__).parent / "logo.png", "rb") as f:
        while chunk := await f.read(16384):
            chunk = remainder + chunk
            encodable = len(chunk)
            encodable -= encodable % 3
            yield base64.b64encode(chunk[:encodable])
            remainder = chunk[encodable:]
    if remainder:
        yield base64.b64encode(remainder)

async def flush_state():
    async with async_open(config.data_dir / "state.json.tmp", "w") as f:
        f: TextFileWrapper
        await f.write(state.model_dump_json())

    os.replace(config.data_dir / "state.json.tmp", config.data_dir / "state.json")

async def get_playlist(playlist_id: UUID) -> list[UUID]:
    # Using GET /Playlists/{id} is preferred due to lower traffic, but requires user token
    # Provided account has no right to do that
    # As such, only GET /Items is available
    # also requires recursive=true for some reason
    resp = await api_client.get(f"/Items?parentId={playlist_id.hex}&recursive=true")
    resp.raise_for_status()
    return [UUID(item["Id"]) for item in resp.json()["Items"]]

async def get_user_favourite_tracks(user_id: UUID) -> list[UUID]:
    # idk where's recursion, you simply filter database and that's it
    # but without recursive=true it added ALL AVAILABLE TRACKS to one playlist
    resp = await api_client.get(f"/Items?includeItemTypes=Audio&filters=IsFavorite&recursive=true&userId={user_id.hex}")
    resp.raise_for_status()
    favourite_tracks: list[UUID] = [UUID(item["Id"]) for item in resp.json()["Items"]]

    if base_playlist := config.base_playlists.get(user_id):
        playlist = await get_playlist(base_playlist)

        tmp = set(playlist)
        for item_id in list(favourite_tracks):  # copy due to concurrent modification
            if item_id in tmp:
                favourite_tracks.remove(item_id)
        del tmp

        if config.order == "forward":
            favourite_tracks = playlist + favourite_tracks
        else:
            favourite_tracks = favourite_tracks + playlist

    logger.debug(f"{config.base_playlists}, {user_id}, {base_playlist}")

    return favourite_tracks

async def recovery():
    global healthy

    logger.debug("Running background recovery job")

    failed = False
    for user_id in state.playlist_by_user.copy():
        try:
            async with await scoped_lock.on(user_id):  # not needed here but anyway
                playlist_id = state.playlist_by_user[user_id]

                resp = await user_client.get(f"/Playlists/{playlist_id.hex}")
                if resp.status_code == 404:
                    del state.playlist_by_user[user_id]
                    await flush_state()
                    logger.warning(
                        f"Removing playlist {playlist_id} (user {user_id}) from internal state because it is not found on server",
                    )
                    logger.warning(
                        f"This is harmless (if done with jellike offline) but you should avoid removing playlists because they keep order of tracks",
                    )
                    continue
                resp.raise_for_status()

                playlist_items = set(UUID(itemId) for itemId in resp.json()["ItemIds"])
                favourite_tracks = set(await get_user_favourite_tracks(user_id))

                for unfavourited_item_id in playlist_items - favourite_tracks:
                    # error if item is not found in playlist is not documented (so assumed impossible)
                    (await user_client.delete(
                        f"/Playlists/{playlist_id.hex}/Items?entryIds={unfavourited_item_id.hex}",
                    )).raise_for_status()
                for favourited_item_id in favourite_tracks - playlist_items:
                    (await user_client.post(
                        f"/Playlists/{playlist_id.hex}/Items?ids={favourited_item_id.hex}&userId={config.user_id.hex}",
                    )).raise_for_status()
                    if config.order == "reverse":
                        (await user_client.post(
                            f"/Playlists/{playlist_id.hex}/Items/{favourited_item_id.hex}/Move/0",
                        )).raise_for_status()
        except Exception as e:
            logger.error(f"Failed to recover user {user_id}", e)
            failed = True

    if not failed and not healthy:
        logger.info("Successfully recovered; removing unhealthy taint")
        recovery_job.reschedule("interval", hours=1)
        healthy = True
    logger.debug("Recovery job complete")
