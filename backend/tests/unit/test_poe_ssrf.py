import ipaddress
import re
import socket
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from app.services.providers.poe import PoeProvider


class TestPoeSSRF:

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8000/admin",
            "http://127.0.0.1/secrets",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/router",
            "http://172.16.0.1/api",
            "http://[::1]/admin",
            "http://[fe80::1]/link-local",
            "file:///etc/passwd",
            "ftp://evil.com/file",
            "http://0.0.0.0/",
            "http://0177.0.0.1/",
        ],
    )
    def test_rejects_private_and_non_http_urls(self, bad_url: str) -> None:
        result = PoeProvider._sync_download(bad_url)
        assert result is None

    @pytest.mark.parametrize(
        "good_url",
        [
            "https://cdn.example.com/image.png",
            "https://poecdn.net/media/video.mp4",
            "http://public.example.com/file",
        ],
    )
    def test_allows_public_http_urls(self, good_url: str) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"downloaded-data"
        mock_response.geturl.return_value = good_url
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_response)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_cm):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
                result = PoeProvider._sync_download(good_url)

        assert result == b"downloaded-data"

    def test_redirect_target_is_revalidated(self) -> None:
        redirect_response = MagicMock()
        redirect_response.geturl.return_value = "http://192.168.1.1/secret"
        redirect_response.read.return_value = b""

        redirect_cm = MagicMock()
        redirect_cm.__enter__ = MagicMock(return_value=redirect_response)
        redirect_cm.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=redirect_cm):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
                result = PoeProvider._sync_download("http://public.com/redirect")

        assert result is None

    def test_redirect_to_public_allowed(self) -> None:
        redirect_response = MagicMock()
        redirect_response.geturl.return_value = "https://cdn.example.com/file"
        redirect_response.read.return_value = b"redirected-data"

        redirect_cm = MagicMock()
        redirect_cm.__enter__ = MagicMock(return_value=redirect_response)
        redirect_cm.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=redirect_cm):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
                result = PoeProvider._sync_download("http://public.com/redirect")

        assert result == b"redirected-data"

    def test_dns_resolution_failure_returns_none(self) -> None:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            result = PoeProvider._sync_download("https://unresolvable.host.test/file")
        assert result is None
