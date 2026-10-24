import httpx
import pytest

from app.core.http import FetchError, PoliteHttpClient

URL = "https://example.org/feed"


def client(settings, web, sleeps):
    return PoliteHttpClient(settings, transport=httpx.MockTransport(web.handler), sleep=sleeps.append)


def test_retries_transient_5xx_then_succeeds(settings, web, sleeps):
    web.add(URL, httpx.Response(503), httpx.Response(200, content=b"ok"))
    r = client(settings, web, sleeps).get(URL)
    assert r.status_code == 200 and r.attempts == 2


def test_honours_retry_after_on_429(settings, web, sleeps):
    web.add(URL, httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200))
    client(settings, web, sleeps).get(URL)
    assert 7.0 in sleeps


def test_gives_up_after_max_retries(settings, web, sleeps):
    web.add(URL, httpx.Response(502))
    with pytest.raises(FetchError) as exc:
        client(settings, web, sleeps).get(URL)
    assert exc.value.status_code == 502 and exc.value.attempts == settings.http_max_retries + 1


def test_403_is_never_retried(settings, web, sleeps):
    web.add(URL, httpx.Response(403), httpx.Response(200))
    with pytest.raises(FetchError) as exc:
        client(settings, web, sleeps).get(URL)
    assert exc.value.status_code == 403 and exc.value.attempts == 1
    assert len(web.requests) == 1


def test_timeout_is_retried(settings, web, sleeps):
    web.add(URL, httpx.ReadTimeout("slow"), httpx.Response(200))
    assert client(settings, web, sleeps).get(URL).attempts == 2


def test_connection_error_exhausts_retries(settings, web, sleeps):
    web.add(URL, httpx.ConnectError("down"))
    with pytest.raises(FetchError, match="ConnectError"):
        client(settings, web, sleeps).get(URL)


def test_conditional_get_headers_and_304(settings, web, sleeps):
    web.add(URL, httpx.Response(304))
    r = client(settings, web, sleeps).get(URL, etag='"abc"', last_modified="Fri, 23 Oct 2026 19:44:27 GMT")
    assert r.not_modified
    sent = web.requests[0].headers
    assert sent["if-none-match"] == '"abc"' and sent["if-modified-since"].startswith("Fri")


def test_identifying_user_agent(settings, web, sleeps):
    web.add(URL, httpx.Response(200))
    client(settings, web, sleeps).get(URL)
    assert web.requests[0].headers["user-agent"].startswith("newsAnalytics/")


def test_per_host_delay(settings, web, sleeps):
    settings.per_host_delay_s = 5
    web.add(URL, httpx.Response(200))
    c = PoliteHttpClient(settings, transport=httpx.MockTransport(web.handler), sleep=sleeps.append,
                         clock=lambda: 100.0)
    c.get(URL)
    c.get(URL)
    assert sleeps == [5.0]
