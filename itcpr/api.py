"""API client for api.itcpr.org."""

import requests
from typing import List, Dict, Any, Optional
from .auth import Auth
from .config import config
from .utils import get_logger, print_error

logger = get_logger(__name__)

# Import mock API for fallback
try:
    from .mock_api import _mock_api
    MOCK_AVAILABLE = True
except ImportError:
    MOCK_AVAILABLE = False
    _mock_api = None

class APIClient:
    """Client for ITCPR Cloud API."""
    
    def __init__(self, auth: Auth):
        self.auth = auth
        self.api_base = auth.api_base
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        token = self.auth.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated API request."""
        url = f"{self.api_base}{endpoint}"
        headers = self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        try:
            response = requests.request(method, url, headers=headers, timeout=5 if use_mock else 30, **kwargs)
            # If we get 404 and mock is available, we'll handle it in the calling methods
            return response
        except requests.RequestException as e:
            if use_mock:
                logger.debug(f"API request failed, will use mock: {e}")
            else:
                logger.error(f"API request failed: {e}")
            raise
    
    def get_me(self) -> Dict[str, Any]:
        """Get current user/device information."""
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        try:
            response = self._request("GET", "/api/agent/me")
            response.raise_for_status()
            return response.json()
        except (requests.HTTPError, requests.RequestException) as e:
            if use_mock and (isinstance(e, requests.HTTPError) and e.response.status_code == 404):
                logger.info("Backend unavailable, using mock API")
                return _mock_api.get_me()
            raise
    
    def get_repos(self) -> List[Dict[str, Any]]:
        """Get list of assigned repositories."""
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        try:
            response = self._request("GET", "/api/agent/repos")
            response.raise_for_status()
            data = response.json()
            return data.get("repos", [])
        except (requests.HTTPError, requests.RequestException) as e:
            if use_mock and (isinstance(e, requests.HTTPError) and e.response.status_code == 404):
                logger.info("Backend unavailable, using mock API")
                return _mock_api.get_repos()
            raise
    
    def get_github_token(self, repo_name: Optional[str] = None) -> str:
        """Get short-lived GitHub installation token."""
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        payload = {}
        if repo_name:
            payload["repo"] = repo_name
        
        try:
            response = self._request("POST", "/api/agent/token", json=payload)
            response.raise_for_status()
            data = response.json()
            token = data.get("token")
            if not token:
                raise ValueError("Token not found in response")
            return token
        except (requests.HTTPError, requests.RequestException) as e:
            if use_mock and (isinstance(e, requests.HTTPError) and e.response.status_code == 404):
                logger.info("Backend unavailable, using mock API")
                return _mock_api.get_github_token(repo_name)
            raise
    
    def validate_token(self) -> bool:
        """Validate current device token."""
        try:
            self.get_me()
            return True
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                return False
            raise
        except Exception:
            return False
    
    def create_repo(self, name: str, description: str = "", private: bool = False, template: Optional[str] = "project-template") -> Dict[str, Any]:
        """Create a new repository in the organization."""
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        payload = {
            "name": name,
            "description": description,
            "visibility": "private" if private else "public"
        }
        
        if template:
            payload["template"] = template
        
        try:
            response = self._request("POST", "/cloud/app/org/repos", json=payload)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 422:
                # GitHub API returns 422 when repo already exists
                error_data = e.response.json()
                error_message = error_data.get("message", "Repository already exists")
                if "already exists" in error_message.lower() or "name already exists" in error_message.lower():
                    raise ValueError(f"Repository '{name}' already exists in the organization. Please choose a different name.")
                raise ValueError(error_message)
            if use_mock and e.response.status_code == 404:
                logger.info("Backend unavailable, using mock API")
                if MOCK_AVAILABLE:
                    return _mock_api.create_repo(name, description, private)
            raise
        except (requests.RequestException, Exception) as e:
            if use_mock:
                logger.info("Backend unavailable, using mock API")
                if MOCK_AVAILABLE:
                    return _mock_api.create_repo(name, description, private)
            raise
    
    def add_collaborator(self, owner: str, repo: str, username: str, permission: str = "admin") -> bool:
        """Add a collaborator to a repository."""
        use_mock = config.mock_mode or (MOCK_AVAILABLE and _mock_api is not None)
        
        payload = {"permission": permission}
        
        try:
            response = self._request("PUT", f"/cloud/app/repos/{owner}/{repo}/collaborators/{username}", json=payload)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            if use_mock and e.response.status_code == 404:
                logger.info("Backend unavailable, using mock API")
                # Mock would silently succeed
                return True
            logger.warning(f"Failed to add collaborator: {e}")
            raise
        except (requests.RequestException, Exception) as e:
            if use_mock:
                logger.info("Backend unavailable, using mock API")
                return True
            logger.warning(f"Failed to add collaborator: {e}")
            raise

