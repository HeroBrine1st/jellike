This is a rework from scratch of https://github.com/Groovbox/jellyfin-liked-playlist.

This work:

- supports multiple users
- has catch-up/recovery task (although order is not guaranteed due to jellyfin limitations)
- supports "base" playlist which is copied into liked playlist in the same order (only for migration - severely decreases performance due to additional checks)
- supports selecting order of tracks (adding new tracks to the start or to the end)
- supports healthchecks including tainting on first failure (disables itself and tries to recover each minute)
- is async!

At the time of release it hasn't been thoroughly tested. It is tested enough to say this works as intended without problems and has multiple safeguards against possible bugs including race condition ones, but was not battle-tested enough to be 100% sure (it works without problems on my deployment, but I don't actively use it yet).

# Installation

- (Only if using `reverse` order) Reverse order works only with PR [jellyfin/jellyfin#13730](https://github.com/jellyfin/jellyfin/pull/13730) applied.
  It is applied in Jellyfin 10.11 and can be cleanly applied on v10.10.7 tag.
- (Optional, but you really should...) Create a service user on your server. Service user owns all playlists created, and because they all are
  named the same, you will quickly start losing the right one. Also making service user allows for proper read-only semantics on playlists,
  avoiding additional problems.  
  This user doesn't need any privileged rights. Add access to music library and allow to keep one session.
- Use [get_user_token.py](get_user_token.py) with (service) user to get user id and token.
  The token goes into `USER_TOKEN` environment variable and id goes into `USER_ID`.
- Create API Token (Dashboard -> API Keys). This goes into `API_TOKEN`.
- Configure the jellike:
  - Set `JELLYFIN_URL` to address of jellyfin server
  - Set `DATA_DIR` to directory for data of jellify (it is two files and one of them is ephemeral)
  - Optionally, set `ORDER` to `REVERSE` if you would like to add tracks to start of liked playlists
  - Optionally, set the port using `PORT` variable and set listen host using `HOST` variable
  - Optionally, if you already have some sort of liked playlist, you can set `BASE_PLAYLISTS` to `:`-separated pair of `USER_ID=PLAYLIST_ID`. 
    Take ids from address bar in browser when respective page is opened.
  The description of all options is available in [config.py](jellike/config.py).
- You can start it via docker (adding to e.g. docker-compose.yml) or your own way. For example, that's my deployment:
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
- Install "Webhooks" plugin
- Create webhook pointing to `/webhook` path of Jellify (e.g. on my deployment it is `http://jellify:8000/webhook`)
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
