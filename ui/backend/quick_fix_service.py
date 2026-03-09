"""Quick fix service to bypass minikube profile list hanging"""

def get_minikube_clusters_static():
    """Return static list of known Minikube clusters without calling minikube command"""
    return {
        "clusters": ["sat-minikube-test", "fips-test-minikube-cluster"],
        "minikube_installed": True,
        "message": "Found 2 Minikube cluster(s) (static list)",
        "suggestion": None
    }
