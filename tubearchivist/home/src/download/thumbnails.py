"""
functionality:
- handle download and caching for thumbnails
- check for missing thumbnails
"""

import base64
import os
from io import BytesIO
from time import sleep

import requests
from home.src.download import queue  # partial import
from home.src.es.connect import IndexPaginate
from home.src.ta.config import AppConfig
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image, ImageFile, ImageFilter, UnidentifiedImageError

ImageFile.LOAD_TRUNCATED_IMAGES = True


class ThumbManagerBase:
    """base class for thumbnail management"""

    CONFIG = AppConfig().config
    CACHE_DIR = CONFIG["application"]["cache_dir"]
    VIDEO_DIR = os.path.join(CACHE_DIR, "videos")
    CHANNEL_DIR = os.path.join(CACHE_DIR, "channels")
    PLAYLIST_DIR = os.path.join(CACHE_DIR, "playlists")

    def __init__(self, item_id, item_type, fallback=False):
        self.item_id = item_id
        self.item_type = item_type
        self.fallback = fallback

    def download_raw(self, url):
        """download thumbnail for video"""
        if not url:
            return self.get_fallback()

        for i in range(3):
            try:
                response = requests.get(url, stream=True, timeout=5)
                if response.ok:
                    try:
                        return Image.open(response.raw)
                    except UnidentifiedImageError:
                        print(f"failed to open thumbnail: {url}")
                        return self.get_fallback()

                if response.status_code == 404:
                    return self.get_fallback()

            except requests.exceptions.RequestException:
                print(f"{self.item_id}: retry thumbnail download {url}")
                sleep((i + 1) ** i)

        return False

    def get_fallback(self):
        """get fallback thumbnail if not available"""
        if self.fallback:
            img_raw = Image.open(self.fallback)
            return img_raw

        app_root = self.CONFIG["application"]["app_root"]
        default_map = {
            "video": os.path.join(
                app_root, "static/img/default-video-thumb.jpg"
            ),
            "playlist": os.path.join(
                app_root, "static/img/default-video-thumb.jpg"
            ),
            "icon": os.path.join(
                app_root, "static/img/default-channel-icon.jpg"
            ),
            "banner": os.path.join(
                app_root, "static/img/default-channel-banner.jpg"
            ),
        }

        img_raw = Image.open(default_map[self.item_type])

        return img_raw


class ThumbManager(ThumbManagerBase):
    """handle thumbnails related functions"""

    def __init__(self, item_id, item_type="video", fallback=False):
        super().__init__(item_id, item_type, fallback=fallback)

    def download(self, url):
        """download thumbnail"""
        print(f"{self.item_id}: download {self.item_type} thumbnail")
        if self.item_type == "video":
            self.download_video_thumb(url)
        elif self.item_type == "channel":
            self.download_channel_art(url)
        elif self.item_type == "playlist":
            self.download_playlist_thumb(url)

    def delete(self):
        """delete thumbnail file"""
        print(f"{self.item_id}: delete {self.item_type} thumbnail")
        if self.item_type == "video":
            self.delete_video_thumb()
        elif self.item_type == "channel":
            self.delete_channel_thumb()
        elif self.item_type == "playlist":
            self.delete_playlist_thumb()

    def download_video_thumb(self, url, skip_existing=False):
        """pass url for video thumbnail"""
        folder_path = os.path.join(self.VIDEO_DIR, self.item_id[0].lower())
        thumb_path = self.vid_thumb_path(absolute=True)

        if skip_existing and os.path.exists(thumb_path):
            return

        os.makedirs(folder_path, exist_ok=True)
        img_raw = self.download_raw(url)
        width, height = img_raw.size

        if not width / height == 16 / 9:
            new_height = width / 16 * 9
            offset = (height - new_height) / 2
            img_raw = img_raw.crop((0, offset, width, height - offset))

        img_raw.convert("RGB").save(thumb_path)

    def vid_thumb_path(self, absolute=False, create_folder=False):
        """build expected path for video thumbnail from youtube_id"""
        folder_name = self.item_id[0].lower()
        folder_path = os.path.join("videos", folder_name)
        thumb_path = os.path.join(folder_path, f"{self.item_id}.jpg")
        if absolute:
            thumb_path = os.path.join(self.CACHE_DIR, thumb_path)

        if create_folder:
            folder_path = os.path.join(self.CACHE_DIR, folder_path)
            os.makedirs(folder_path, exist_ok=True)

        return thumb_path

    def download_channel_art(self, urls, skip_existing=False):
        """pass tuple of channel thumbnails"""
        channel_thumb, channel_banner = urls
        self._download_channel_thumb(channel_thumb, skip_existing)
        self._download_channel_banner(channel_banner, skip_existing)

    def _download_channel_thumb(self, channel_thumb, skip_existing):
        """download channel thumbnail"""

        thumb_path = os.path.join(
            self.CHANNEL_DIR, f"{self.item_id}_thumb.jpg"
        )
        self.item_type = "icon"

        if skip_existing and os.path.exists(thumb_path):
            return

        img_raw = self.download_raw(channel_thumb)
        img_raw.convert("RGB").save(thumb_path)

    def _download_channel_banner(self, channel_banner, skip_existing):
        """download channel banner"""

        banner_path = os.path.join(
            self.CHANNEL_DIR, self.item_id + "_banner.jpg"
        )
        self.item_type = "banner"
        if skip_existing and os.path.exists(banner_path):
            return

        img_raw = self.download_raw(channel_banner)
        img_raw.convert("RGB").save(banner_path)

    def download_playlist_thumb(self, url, skip_existing=False):
        """pass thumbnail url"""
        thumb_path = os.path.join(self.PLAYLIST_DIR, f"{self.item_id}.jpg")
        if skip_existing and os.path.exists(thumb_path):
            return

        img_raw = self.download_raw(url)
        img_raw.convert("RGB").save(thumb_path)

    def delete_video_thumb(self):
        """delete video thumbnail if exists"""
        thumb_path = self.vid_thumb_path()
        to_delete = os.path.join(self.CACHE_DIR, thumb_path)
        if os.path.exists(to_delete):
            os.remove(to_delete)

    def delete_channel_thumb(self):
        """delete all artwork of channel"""
        thumb = os.path.join(self.CHANNEL_DIR, f"{self.item_id}_thumb.jpg")
        banner = os.path.join(self.CHANNEL_DIR, f"{self.item_id}_banner.jpg")
        if os.path.exists(thumb):
            os.remove(thumb)
        if os.path.exists(banner):
            os.remove(banner)

    def delete_playlist_thumb(self):
        """delete playlist thumbnail"""
        thumb_path = os.path.join(self.PLAYLIST_DIR, f"{self.item_id}.jpg")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

    def get_vid_base64_blur(self):
        """return base64 encoded placeholder"""
        file_path = os.path.join(self.CACHE_DIR, self.vid_thumb_path())
        img_raw = Image.open(file_path)
        img_raw.thumbnail((img_raw.width // 20, img_raw.height // 20))
        img_blur = img_raw.filter(ImageFilter.BLUR)
        buffer = BytesIO()
        img_blur.save(buffer, format="JPEG")
        img_data = buffer.getvalue()
        img_base64 = base64.b64encode(img_data).decode()
        data_url = f"data:image/jpg;base64,{img_base64}"

        return data_url


class ValidatorCallback:
    """handle callback validate thumbnails page by page"""

    def __init__(self, source, index_name):
        self.source = source
        self.index_name = index_name

    def run(self):
        """run the task for page"""
        print(f"{self.index_name}: validate artwork")
        if self.index_name == "ta_video":
            self._validate_videos()
        elif self.index_name == "ta_channel":
            self._validate_channels()
        elif self.index_name == "ta_playlist":
            self._validate_playlists()

    def _validate_videos(self):
        """check if video thumbnails are correct"""
        for video in self.source:
            url = video["_source"]["vid_thumb_url"]
            handler = ThumbManager(video["_source"]["youtube_id"])
            handler.download_video_thumb(url, skip_existing=True)

    def _validate_channels(self):
        """check if all channel artwork is there"""
        for channel in self.source:
            urls = (
                channel["_source"]["channel_thumb_url"],
                channel["_source"]["channel_banner_url"],
            )
            handler = ThumbManager(channel["_source"]["channel_id"])
            handler.download_channel_art(urls, skip_existing=True)

    def _validate_playlists(self):
        """check if all playlist artwork is there"""
        for playlist in self.source:
            url = playlist["_source"]["playlist_thumbnail"]
            handler = ThumbManager(playlist["_source"]["playlist_id"])
            handler.download_playlist_thumb(url, skip_existing=True)


class ThumbValidator:
    """validate thumbnails"""

    def download_missing(self):
        """download all missing artwork"""
        self.download_missing_videos()
        self.download_missing_channels()
        self.download_missing_playlists()

    def download_missing_videos(self):
        """get all missing video thumbnails"""
        data = {
            "query": {"term": {"active": {"value": True}}},
            "sort": [{"youtube_id": {"order": "asc"}}],
            "_source": ["vid_thumb_url", "youtube_id"],
        }
        paginate = IndexPaginate(
            "ta_video", data, size=5000, callback=ValidatorCallback
        )
        _ = paginate.get_results()

    def download_missing_channels(self):
        """get all missing channel thumbnails"""
        data = {
            "query": {"term": {"channel_active": {"value": True}}},
            "sort": [{"channel_id": {"order": "asc"}}],
            "_source": {
                "excludes": ["channel_description", "channel_overwrites"]
            },
        }
        paginate = IndexPaginate(
            "ta_channel", data, callback=ValidatorCallback
        )
        _ = paginate.get_results()

    def download_missing_playlists(self):
        """get all missing playlist artwork"""
        data = {
            "query": {"term": {"playlist_active": {"value": True}}},
            "sort": [{"playlist_id": {"order": "asc"}}],
            "_source": ["playlist_id", "playlist_thumbnail"],
        }
        paginate = IndexPaginate(
            "ta_playlist", data, callback=ValidatorCallback
        )
        _ = paginate.get_results()


class ThumbFilesystem:
    """filesystem tasks for thumbnails"""

    CONFIG = AppConfig().config
    CACHE_DIR = CONFIG["application"]["cache_dir"]
    MEDIA_DIR = CONFIG["application"]["videos"]
    VIDEO_DIR = os.path.join(CACHE_DIR, "videos")

    def sync(self):
        """embed thumbnails to mediafiles"""
        video_list = self.get_thumb_list()
        self._embed_thumbs(video_list)

    def get_thumb_list(self):
        """get list of mediafiles and matching thumbnails"""
        pending = queue.PendingList()
        pending.get_download()
        pending.get_indexed()

        video_list = []
        for video in pending.all_videos:
            video_id = video["youtube_id"]
            media_url = os.path.join(self.MEDIA_DIR, video["media_url"])
            thumb_path = os.path.join(
                self.CACHE_DIR, ThumbManager(video_id).vid_thumb_path()
            )
            video_list.append(
                {
                    "media_url": media_url,
                    "thumb_path": thumb_path,
                }
            )

        return video_list

    @staticmethod
    def _embed_thumbs(video_list):
        """rewrite the thumbnail into media file"""

        counter = 1
        for video in video_list:
            # loop through all videos
            media_url = video["media_url"]
            thumb_path = video["thumb_path"]

            mutagen_vid = MP4(media_url)
            with open(thumb_path, "rb") as f:
                mutagen_vid["covr"] = [
                    MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)
                ]
            mutagen_vid.save()
            if counter % 50 == 0:
                print(f"thumbnail write progress {counter}/{len(video_list)}")
            counter = counter + 1
