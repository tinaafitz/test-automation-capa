"""
Tests for OCM version parsing, ordering and pre-release handling.

Motivating bug: list_versions() filtered on `len(raw_id.split(".")) == 3`, so
"5.0.0-rc.0" (four parts) was silently dropped — a version that provisions
fine could never reach the UI.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.ocm_client import (  # noqa: E402
    VERSION_RE,
    OCMClient,
    is_prerelease,
    version_sort_key,
)


class TestVersionRegex:
    @pytest.mark.parametrize("version", [
        "4.20.12", "4.22.13", "5.0.0", "5.0.0-rc.0", "5.0.0-rc.1", "4.7.0-assembly.art3091",
    ])
    def test_accepts(self, version):
        assert VERSION_RE.match(version)

    @pytest.mark.parametrize("version", ["4.20", "abc", "", "v4.20.12", "4.20.12.3"])
    def test_rejects(self, version):
        assert not VERSION_RE.match(version)


class TestIsPrerelease:
    def test_release(self):
        assert not is_prerelease("5.0.0")

    def test_prerelease(self):
        assert is_prerelease("5.0.0-rc.0")

    def test_garbage_is_not_prerelease(self):
        assert not is_prerelease("not-a-version")


class TestVersionSortKey:
    def test_numeric_not_lexicographic(self):
        # OCM's own `order=id desc` puts 4.9.0 above 4.20.12.
        assert sorted(["4.9.0", "4.20.12"], key=version_sort_key, reverse=True) == \
            ["4.20.12", "4.9.0"]

    def test_release_outranks_its_prereleases(self):
        assert sorted(["5.0.0-rc.1", "5.0.0"], key=version_sort_key, reverse=True) == \
            ["5.0.0", "5.0.0-rc.1"]

    def test_prereleases_compare_numerically(self):
        assert sorted(["5.0.0-rc.2", "5.0.0-rc.10"], key=version_sort_key, reverse=True) == \
            ["5.0.0-rc.10", "5.0.0-rc.2"]

    def test_full_ordering(self):
        versions = ["4.9.0", "4.20.12", "5.0.0", "5.0.0-rc.1", "5.0.0-rc.0", "4.22.13"]
        assert sorted(versions, key=version_sort_key, reverse=True) == [
            "5.0.0", "5.0.0-rc.1", "5.0.0-rc.0", "4.22.13", "4.20.12", "4.9.0",
        ]

    def test_unparseable_sorts_last(self):
        assert sorted(["garbage", "4.20.12"], key=version_sort_key, reverse=True) == \
            ["4.20.12", "garbage"]


def _client_with_items(items, total=None):
    client = OCMClient(client_id="id", client_secret="secret")
    pages = []

    def fake_request(url):
        pages.append(url)
        return {"items": items, "total": total if total is not None else len(items)}

    client._authed_request = fake_request
    return client, pages


class TestListVersions:
    def test_keeps_prerelease_builds(self):
        client, _ = _client_with_items([
            {"raw_id": "4.22.13"},
            {"raw_id": "5.0.0-rc.0"},
        ])
        versions, err = client.list_versions("candidate")
        assert err is None
        assert "5.0.0-rc.0" in versions

    def test_sorts_newest_first(self):
        client, _ = _client_with_items([
            {"raw_id": "4.9.0"}, {"raw_id": "4.22.13"}, {"raw_id": "4.20.12"},
        ])
        versions, _ = client.list_versions("stable")
        assert versions == ["4.22.13", "4.20.12", "4.9.0"]

    def test_strips_openshift_prefix(self):
        client, _ = _client_with_items([{"id": "openshift-v4.22.13"}])
        versions, _ = client.list_versions("stable")
        assert versions == ["4.22.13"]

    def test_drops_unparseable_ids(self):
        client, _ = _client_with_items([{"raw_id": "4.22.13"}, {"raw_id": "nightly-build"}])
        versions, _ = client.list_versions("stable")
        assert versions == ["4.22.13"]

    def test_paginates_past_first_page(self):
        client, pages = _client_with_items([{"raw_id": "4.22.13"}], total=250)
        client.list_versions("candidate")
        assert len(pages) == 3
        assert "page=1" in pages[0] and "page=3" in pages[2]

    def test_stops_when_page_is_empty(self):
        client, pages = _client_with_items([], total=999)
        versions, _ = client.list_versions("candidate")
        assert versions == []
        assert len(pages) == 1
