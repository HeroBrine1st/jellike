This is a rework from scratch of https://github.com/Groovbox/jellyfin-liked-playlist.

This work:

- supports multiple users
- has catch-up/recovery task (although order is not guaranteed due to jellyfin limitations)
- supports "base" playlist which is copied into liked playlist in the same order (only for migration - severely decreases performance due to additional checks)
- supports selecting order of tracks (adding new tracks to the start or to the end)
- supports healthchecks including tainting on first failure (disables itself and tries to recover each minute)
- is async!

This service is developed against Jellyfin 10.10.7 but supports 10.11 branch. It could, possibly, support 12.x branch without changes, too, and so on. It's also not exposed to users in any way and can, given an option, be migrated to another service in future or even to native Jellyfin support (although the latter would require a simple script).

The point is, unless it breaks, there won't be any updates, including this README. Anyway it's easy to try! The installation is non-invasive and can be removed at any time by reverting the changes.

# Installation

- (Only if using `reverse` order) Reverse order works only with PR [jellyfin/jellyfin#13730](https://github.com/jellyfin/jellyfin/pull/13730) applied.
  It is applied in Jellyfin 10.11 and can be cleanly applied on v10.10.7 tag.
- (Optional, but you really should...) Create a service user on your server. That user owns all playlists created by this service, and because they all are
  named the same, you will quickly start losing the right one if you use your own user and have multiple users on your server.
  Also, having a dedicated user allows for proper read-only semantics on playlists, avoiding additional problems.
  This user doesn't need any privileged rights. Add access to music library and allow to keep one session.  
  Note that "service user" is not some type of Jellyfin user but a regular user, simply used for a *service*.
- Use [get_user_token.py](get_user_token.py) with (service) user to get user id and token.
  The token goes into `USER_TOKEN` environment variable and id goes into `USER_ID`.
- Create API Token (Dashboard -> API Keys). This goes into `API_TOKEN`.
- Configure the jellike. Config is fairly documented in [config.py](jellike/config.py), but here are the essentials:
  - Set `JELLYFIN_URL` to base URL of your jellyfin server
  - Set `DATA_DIR` to a path where jellike will store its state (it is two files and one of them is ephemeral)
  - Optionally, set `ORDER` to `reverse` if you would like to add tracks to start of liked playlists
  - Optionally, set the port using `PORT` variable and set listen host using `HOST` variable
  - Optionally, if you already have some sort of liked playlist, you can set `BASE_PLAYLISTS` to `:`-separated pairs of `USER_ID=PLAYLIST_ID`. 
    Take ids from address bar in browser when respective page is opened.  
- Start the service. Docker Compose example (assuming repo is available at `jellike` folder near `docker-compose.yml`).
  ```yaml
  services:
    jellyfin:
      ...
    jellike:
      build: ./jellike
      user: nobody
      restart: unless-stopped
      environment:
        USER_ID: "..."
        USER_TOKEN: "..."
        API_TOKEN: "..."
        JELLYFIN_URL: "http://jellyfin:8096"
        DATA_DIR: /data
        ORDER: reverse
      volumes:
        - ./jellike_data:/data
      depends_on:
        jellyfin:
          condition: service_healthy
  ```
  After service is started, it will try to catch up on its known users (it knows none) and then start listening on webhook, which is not configured yet. For now, the service is dormant.
- Install "Webhooks" plugin
- Create webhook pointing to `/webhook` path of Jellike (e.g. on my deployment it is `http://jellike:8000/webhook`)
  - Template:
    ```
    {{#if_equals SaveReason "UpdateUserRating"}}
    {
        "item_id": "{{ItemId}}",
        "is_favourite": {{#if Favorite}}true{{else}}false{{/if}},
        "user_id": "{{UserId}}"
    }
    {{/if_equals}}
    ```
  - Add request header: `Content-Type`: `application/json`
  - Notification type - check only "User Data Saved"
  - Item type - check only "Songs"
  - Do not send when message body is empty - check
- Try adding liked track. You should see created playlist after that and after 5 seconds the logo will be updated.
  If logo is not updated and you see no errors in logs of jellike, try increasing `DELAY_BEFORE_UPLOAD_PLAYLIST_IMAGE_SECONDS` to bigger delay.
  This can be required on slow machines because jellyfin replaces `Primary` image after it completes its generation.
- You should see your liked tracks inside playlist. If so, installation complete!

# Copyright

```
Jellike is a Jellyfin sidecar service adding "Liked songs" playlist
Copyright (C) 2025 HeroBrine1st Erquilenne <jellike-project@herobrine1st.ru>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

# Known bugs

There is a very brief period at service startup/recovery after it catched up to updates but isn't started handling requests, found after quickly skimming through code to update README.md file due to natural habit of the developer to spot race conditions in written code.

On startup, it ill do a recovery pass, start up and then do one again after one minute and as such data loss is not that probable if startup is successful. It requires $N>1$ likes by the same user in one minute and then it's $\frac{1}{N!}$ probability on top of that. However, if it not successful, it will do recovery pass after $M \in \mathbb{N}$ minutes (until e.g. jellyfin is available) and then after one hour (recurring each hour if everything's okay) and as such data loss is more probable.

It is both a race condition class bug (startup code, fix is ~4 line changes) and ACID violation class bug (recovery code, non-trivial fix), and not trivial to fix due to inability to make a transactional request from Webhooks plugin.

There's no reports of this bug to ever occur, and it only impacts order of new tracks, but not old ones.
