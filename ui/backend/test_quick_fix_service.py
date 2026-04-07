"""Tests for quick_fix_service module."""

from quick_fix_service import get_minikube_clusters_static


class TestGetMinikubeClustersStatic:
    def test_returns_expected_structure(self):
        result = get_minikube_clusters_static()
        assert "clusters" in result
        assert "minikube_installed" in result
        assert "message" in result
        assert "suggestion" in result

    def test_returns_known_clusters(self):
        result = get_minikube_clusters_static()
        assert isinstance(result["clusters"], list)
        assert len(result["clusters"]) == 2
        assert "sat-minikube-test" in result["clusters"]
        assert "fips-test-minikube-cluster" in result["clusters"]

    def test_minikube_installed_true(self):
        result = get_minikube_clusters_static()
        assert result["minikube_installed"] is True

    def test_suggestion_is_none(self):
        result = get_minikube_clusters_static()
        assert result["suggestion"] is None

    def test_message_contains_count(self):
        result = get_minikube_clusters_static()
        assert "2" in result["message"]
