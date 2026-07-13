import json
import re
import urllib.parse
import subprocess
import os
import sys
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class AudioFormat:
    itag: int
    mime_type: str
    bitrate: int
    audio_quality: str
    url: Optional[str] = None
    signature_cipher: Optional[str] = None

@dataclass
class AudioTrack:
    title: str
    author: str
    video_id: str
    duration: int
    is_live: bool

class YouTubeAudioExtractor:
    AUDIO_PRIORITY = [
        (251, "opus @160kbps", "audio/webm"),
        (250, "opus @70kbps", "audio/webm"),
        (249, "opus @50kbps", "audio/webm"),
        (140, "m4a @128kbps", "audio/mp4"),
        (256, "m4a @128kbps", "audio/mp4"),
        (258, "m4a @128kbps", "audio/mp4"),
        (139, "m4a @48kbps", "audio/mp4"),
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'})
        self.visitor_data = None
        self.player_script = None
        self.signature_timestamp = None

    def fetch_visitor_data(self) -> Optional[str]:
        try:
            r = self.session.get('https://www.youtube.com/embed', timeout=10)
            if r.status_code == 200:
                m = re.search(r'"VISITOR_DATA":"([^"]+)"', r.text)
                if m:
                    self.visitor_data = m.group(1)
                    return self.visitor_data
        except:
            pass
        return None

    def fetch_player_script(self, video_id: str = "dQw4w9WgXcQ") -> Optional[str]:
        try:
            r = self.session.get(f'https://www.youtube.com/embed/{video_id}', timeout=10)
            if r.status_code == 200:
                m = re.search(r'"jsUrl":"([^"]+)"', r.text)
                if m:
                    script_url = m.group(1)
                    if not script_url.startswith('http'):
                        script_url = f"https://www.youtube.com{script_url}"
                    script_url = re.sub(r'/[a-z]{2}_[A-Z]{2}/', '/en_US/', script_url)
                    sr = self.session.get(script_url, timeout=10)
                    if sr.status_code == 200:
                        ts = re.search(r'(?:signatureTimestamp|sts):(\d+)', sr.text)
                        if ts:
                            self.signature_timestamp = ts.group(1)
                            self.player_script = script_url
                            return script_url
        except:
            pass
        return None

    def extract_video_id(self, url: str) -> Optional[str]:
        patterns = [
            r'(?:v=|\/shorts\/|youtu\.be\/)([^&?]+)',
            r'youtube\.com\/watch\?v=([^&?]+)',
            r'youtube\.com\/live\/([^&?]+)',
            r'youtu\.be\/([^&?]+)'
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    def make_player_request(self, video_id: str, client_type: str = 'WEB') -> Optional[Dict[str, Any]]:
        if not self.visitor_data:
            self.fetch_visitor_data()
        if not self.player_script:
            self.fetch_player_script(video_id)

        clients = {
            'WEB': {
                'clientName': 'WEB',
                'clientVersion': '2.20260114.01.00',
                'platform': 'DESKTOP',
                'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            },
            'ANDROID': {
                'clientName': 'ANDROID',
                'clientVersion': '20.01.35',
                'platform': 'MOBILE',
                'userAgent': 'com.google.android.youtube/20.01.35 (Linux; U; Android 14) identity',
                'deviceMake': 'Google',
                'deviceModel': 'Pixel 6',
                'osName': 'Android',
                'osVersion': '14',
                'androidSdkVersion': '34'
            }
        }
        client = clients.get(client_type, clients['WEB'])
        payload = {
            "context": {"client": client, "user": {"lockedSafetyMode": False}, "request": {"useSsl": True}},
            "videoId": video_id,
            "contentCheckOk": True,
            "racyCheckOk": True
        }
        if self.visitor_data:
            payload["context"]["client"]["visitorData"] = self.visitor_data
        if self.signature_timestamp and client_type == 'WEB':
            payload["playbackContext"] = {"contentPlaybackContext": {"signatureTimestamp": self.signature_timestamp}}

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': client['userAgent'],
            'X-Goog-Visitor-Id': self.visitor_data or '',
            'X-YouTube-Client-Name': '1' if client_type == 'WEB' else '3',
            'X-YouTube-Client-Version': client['clientVersion'],
            'Origin': 'https://www.youtube.com',
            'Referer': 'https://www.youtube.com/'
        }
        try:
            r = self.session.post('https://www.youtube.com/youtubei/v1/player', json=payload, headers=headers, timeout=15)
            if r.status_code != 200:
                return None
            data = r.json()
            if 'error' in data:
                return None
            return data
        except:
            return None

    def parse_audio_formats(self, streaming_data: Dict[str, Any]) -> List[AudioFormat]:
        audio_formats = []
        formats = streaming_data.get('formats', []) + streaming_data.get('adaptiveFormats', [])
        for fmt in formats:
            mime = fmt.get('mimeType', '')
            if not mime.startswith('audio/'):
                continue
            url = fmt.get('url')
            cipher = fmt.get('signatureCipher')
            if cipher and not url:
                try:
                    params = urllib.parse.parse_qs(cipher)
                    url = params.get('url', [''])[0]
                    sig = params.get('s', [''])[0]
                    if sig and sig.endswith('='):
                        resolved = sig[::-1]
                        if '&sig=' in url:
                            url = re.sub(r'&sig=[^&]+', f'&sig={resolved}', url)
                        else:
                            url += f'&sig={resolved}'
                except:
                    continue
            if not url:
                continue
            audio_formats.append(AudioFormat(
                itag=fmt.get('itag', 0),
                mime_type=mime,
                bitrate=fmt.get('bitrate', 0),
                audio_quality=fmt.get('audioQuality', 'UNKNOWN'),
                url=url,
                signature_cipher=cipher
            ))
        return audio_formats

    def select_best_audio(self, audio_formats: List[AudioFormat]) -> Optional[AudioFormat]:
        if not audio_formats:
            return None
        priority = {itag: idx for idx, (itag, _, _) in enumerate(self.AUDIO_PRIORITY)}
        valid = [f for f in audio_formats if f.url]
        if not valid:
            return None
        valid.sort(key=lambda f: (priority.get(f.itag, 999), -f.bitrate))
        return valid[0]

    def get_track_info(self, player_response: Dict[str, Any]) -> Optional[AudioTrack]:
        vd = player_response.get('videoDetails', {})
        if not vd:
            return None
        duration = int(vd.get('lengthSeconds', 0))
        return AudioTrack(
            title=vd.get('title', 'Unknown'),
            author=vd.get('author', 'Unknown'),
            video_id=vd.get('videoId', ''),
            duration=duration,
            is_live=vd.get('isLiveContent', False)
        )

    def _format_duration(self, seconds: int) -> str:
        if seconds <= 0:
            return "🔴 LIVE"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    def _get_format_description(self, itag: int) -> str:
        return dict(self.AUDIO_PRIORITY).get(itag, f"itag {itag}")

    def extract_audio_url(self, url: str) -> Optional[Dict[str, Any]]:
        video_id = self.extract_video_id(url)
        if not video_id:
            return None
        logger.info(f"Extracting audio for video ID: {video_id}")

        player_response = None
        for client in ['WEB', 'ANDROID']:
            logger.info(f"Trying client: {client}")
            resp = self.make_player_request(video_id, client)
            if resp and 'streamingData' in resp:
                player_response = resp
                logger.info(f"Success with client: {client}")
                break

        if not player_response:
            return None

        playability = player_response.get('playabilityStatus', {})
        if playability.get('status') != 'OK':
            logger.error(f"Not playable: {playability.get('reason')}")
            return None

        track = self.get_track_info(player_response)
        if not track:
            return None

        streaming_data = player_response.get('streamingData', {})
        sabr_url = streaming_data.get('serverAbrStreamingUrl')
        audio_formats = self.parse_audio_formats(streaming_data)
        best = self.select_best_audio(audio_formats)

        result = {
            'title': track.title,
            'author': track.author,
            'video_id': track.video_id,
            'duration': track.duration,
            'duration_formatted': self._format_duration(track.duration),
            'is_live': track.is_live,
            'all_formats': [{'itag': f.itag, 'bitrate': f.bitrate, 'description': self._get_format_description(f.itag)} for f in (audio_formats[:10] if audio_formats else [])]
        }

        if best and best.url:
            result['url'] = best.url
            result['type'] = 'direct'
            result['format_description'] = self._get_format_description(best.itag)
            result['bitrate'] = best.bitrate
            result['audio_quality'] = best.audio_quality
            return result
        elif sabr_url:
            result['url'] = sabr_url
            result['type'] = 'sabr'
            result['format_description'] = 'SABR (Adaptive)'
            result['bitrate'] = 0
            result['audio_quality'] = 'Adaptive'
            return result
        return None


def find_ffmpeg():
    """Try to locate ffmpeg.exe in the same directory as this script, then in PATH."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg = os.path.join(script_dir, 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    # Check PATH
    for path in os.environ.get('PATH', '').split(os.pathsep):
        exe = os.path.join(path, 'ffmpeg.exe')
        if os.path.exists(exe):
            return exe
    return None

def convert_with_ffmpeg(audio_url: str, output_format: str = 'mp3', output_file: str = None) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.error("ffmpeg.exe not found. Please place it in the same folder as this script.")
        return False

    if output_file is None:
        output_file = f"audio.{output_format}"

    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    headers = f"User-Agent={user_agent}"

    if output_format == 'hls':
        base = os.path.splitext(output_file)[0]
        os.makedirs(os.path.dirname(base) or '.', exist_ok=True)
        cmd = [
            ffmpeg, '-y',
            '-headers', headers,
            '-i', audio_url,
            '-c:a', 'aac',
            '-b:a', '128k',
            '-f', 'hls',
            '-hls_time', '10',
            '-hls_list_size', '0',
            '-hls_segment_filename', f'{base}_%03d.ts',
            f'{base}.m3u8'
        ]
    else:
        codec = 'libmp3lame' if output_format == 'mp3' else 'aac'
        ext = 'mp3' if output_format == 'mp3' else 'm4a'
        if output_file is None:
            output_file = f"audio.{ext}"
        cmd = [
            ffmpeg, '-y',
            '-headers', headers,
            '-i', audio_url,
            '-c:a', codec,
            '-b:a', '128k',
            output_file
        ]

    logger.info(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        logger.info(f"Conversion successful. Output: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg failed: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract YouTube audio and convert to streamable format.")
    parser.add_argument('url', nargs='?', help='YouTube URL')
    parser.add_argument('--convert', choices=['mp3', 'm4a', 'hls'], help='Convert to format using ffmpeg')
    parser.add_argument('--output', help='Output file name (for single files) or base name (for HLS)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    url = args.url
    if not url:
        url = input("Give me URL: --> ").strip()

    extractor = YouTubeAudioExtractor()
    result = extractor.extract_audio_url(url)

    if not result:
        print("❌ Failed to extract audio URL.")
        sys.exit(1)

    print("\n✅ Extraction successful!")
    print("=" * 60)
    print(f"📌 Title: {result['title']}")
    print(f"👤 Artist: {result['author']}")
    print(f"⏱️ Duration: {result['duration_formatted']}")
    print(f"📹 Video ID: {result['video_id']}")
    print("-" * 60)

    if result['type'] == 'direct':
        print(f"🎵 Format: {result['format_description']}")
        print(f"📊 Bitrate: {result['bitrate']:,} bps ({result['bitrate'] // 1000} kbps)")
        print(f"🎧 Quality: {result['audio_quality']}")
    else:
        print(f"🎵 Format: {result['format_description']}")

    print("-" * 60)
    print(f"🔗 Audio URL: {result['url']}")

    if args.convert:
        print(f"\n🔄 Converting to {args.convert.upper()}...")
        success = convert_with_ffmpeg(result['url'], args.convert, args.output)
        if success:
            print("✅ Conversion completed.")
        else:
            print("❌ Conversion failed.")
    else:
        print("\n💡 To convert, run with --convert mp3|m4a|hls")
        print(f"   Example: py lun.py \"{url}\" --convert mp3")


if __name__ == "__main__":
    main()