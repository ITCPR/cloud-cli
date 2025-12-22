"""Authentication management for ITCPR Cloud."""

import keyring
import time
import webbrowser
import requests
import socket
import platform
from typing import Optional, Dict, Any
from .config import config
from .utils import get_logger, print_error, print_success, print_info

logger = get_logger(__name__)

# Import mock API for fallback
try:
    from .mock_api import _mock_api
    MOCK_AVAILABLE = True
except ImportError:
    MOCK_AVAILABLE = False
    _mock_api = None

# Keyring service name
KEYRING_SERVICE = "itcpr"
KEYRING_USERNAME = "device-token"

class Auth:
    """Manages device authentication."""
    
    def __init__(self):
        self.api_base = config.api_base
        self.device_id: Optional[str] = None
        self.device_token: Optional[str] = None
        self._load_token()
    
    def _load_token(self):
        """Load device token from keyring."""
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if token:
                # Token format: device_id:token
                parts = token.split(":", 1)
                if len(parts) == 2:
                    self.device_id, self.device_token = parts
                    logger.debug(f"Loaded device token for device: {self.device_id}")
        except Exception as e:
            logger.debug(f"Could not load token from keyring: {e}")
            self.device_token = None
            self.device_id = None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated (has valid token)."""
        if not self.device_token:
            return False
        
        # Optionally verify token is still valid on server
        # This is a lightweight check - we'll do full validation when needed
        return True
    
    def verify_token(self) -> bool:
        """Verify that the stored token is still valid on the server."""
        if not self.device_token:
            return False
        
        try:
            from .api import APIClient
            api = APIClient(self)
            return api.validate_token()
        except Exception as e:
            logger.debug(f"Token validation failed: {e}")
            return False
    
    def _get_device_name(self) -> str:
        """Get device name (hostname)"""
        try:
            hostname = socket.gethostname()
            # Try to get a more descriptive name on macOS
            if platform.system() == 'Darwin':  # macOS
                try:
                    import subprocess
                    name = subprocess.check_output(['scutil', '--get', 'ComputerName'], text=True).strip()
                    if name:
                        return name
                except:
                    pass
            return hostname or 'Unknown Device'
        except:
            return 'Unknown Device'
    
    def login(self) -> bool:
        """Start device login flow."""
        print_info("Starting device login flow...")
        
        # Try real API first, fall back to mock on 404
        use_mock = False
        try:
            # Step 1: Request device code
            response = requests.post(
                f"{self.api_base}/api/device/start",
                json={},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as e:
            # If 404 and mock is available, use mock
            if e.response.status_code == 404 and MOCK_AVAILABLE and _mock_api is not None:
                logger.info("Backend unavailable (404), using mock API")
                print_info("⚠️  Backend unavailable, using mock mode for testing")
                use_mock = True
                data = _mock_api.device_start()
            else:
                raise
        except requests.RequestException as e:
            # Network error - try mock if available
            if MOCK_AVAILABLE and _mock_api is not None and not config.mock_mode:
                # Only use mock on network errors if explicitly enabled
                raise
            elif MOCK_AVAILABLE and _mock_api is not None:
                logger.info("Network error, using mock API")
                print_info("⚠️  Network error, using mock mode for testing")
                use_mock = True
                data = _mock_api.device_start()
            else:
                raise
        
        device_code = data.get("device_code")
        user_code = data.get("user_code")
        verification_uri = data.get("verification_uri")
        # Replace api.itcpr.org with cloud.itcpr.org for frontend URL
        if verification_uri and "api.itcpr.org" in verification_uri:
            verification_uri = verification_uri.replace("api.itcpr.org", "cloud.itcpr.org")
        expires_in = data.get("expires_in", 600)
        interval = data.get("interval", 5)
        
        # Format user code for display (e.g., ABCD-1234) to match web page
        # Remove any existing hyphens first, then format
        clean_code = user_code.replace('-', '')
        if len(clean_code) == 8:
            # Format as ABCD-1234 (4 chars, hyphen, 4 chars)
            formatted_code = f"{clean_code[:4]}-{clean_code[4:]}"
        else:
            # If not 8 chars, just use as-is
            formatted_code = user_code
        
        print_info(f"\nDevice code: {formatted_code}")
        print_info(f"Please visit: {verification_uri}")
        print_info("\nWaiting for approval...")
        
        # Open browser
        try:
            webbrowser.open(verification_uri)
        except Exception as e:
            logger.debug(f"Could not open browser: {e}")
            print_info("Please open the URL manually in your browser.")
        
        # Step 2: Poll for approval
        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(interval)
            
            try:
                if use_mock:
                    # Use mock API
                    token_data = _mock_api.device_poll(device_code)
                    if token_data is None:
                        print_info(".", end="", flush=True)
                        continue
                else:
                    # Try real API
                    try:
                        # Get device name for header
                        device_name = self._get_device_name()
                        poll_response = requests.get(
                            f"{self.api_base}/api/device/poll",
                            params={"device_code": device_code},
                            headers={"X-Device-Name": device_name},
                            timeout=10
                        )
                        
                        if poll_response.status_code == 200:
                            token_data = poll_response.json()
                        elif poll_response.status_code == 202:
                            # Still waiting
                            print_info(".", end="", flush=True)
                            continue
                        elif poll_response.status_code == 400:
                            error_data = poll_response.json()
                            error = error_data.get("error", "Unknown error")
                            print_error(f"Authentication failed: {error}")
                            return False
                        elif poll_response.status_code == 404 and MOCK_AVAILABLE and _mock_api is not None:
                            # Backend unavailable, switch to mock
                            logger.info("Backend unavailable (404), switching to mock API")
                            use_mock = True
                            token_data = _mock_api.device_poll(device_code)
                            if token_data is None:
                                print_info(".", end="", flush=True)
                                continue
                        else:
                            continue
                    except requests.HTTPError as e:
                        if e.response.status_code == 404 and MOCK_AVAILABLE and _mock_api is not None:
                            # Switch to mock
                            use_mock = True
                            token_data = _mock_api.device_poll(device_code)
                            if token_data is None:
                                print_info(".", end="", flush=True)
                                continue
                        else:
                            raise
                
                device_id = token_data.get("device_id")
                device_token = token_data.get("device_token")
                
                if device_id and device_token:
                    # Store token
                    self.device_id = device_id
                    self.device_token = device_token
                    self._save_token()
                    if use_mock:
                        print_success("Device authenticated successfully! (Mock mode)")
                    else:
                        print_success("Device authenticated successfully!")
                    return True
                
            except requests.RequestException as e:
                logger.debug(f"Poll request failed: {e}")
                if use_mock:
                    # Try mock
                    token_data = _mock_api.device_poll(device_code)
                    if token_data:
                        device_id = token_data.get("device_id")
                        device_token = token_data.get("device_token")
                        if device_id and device_token:
                            self.device_id = device_id
                            self.device_token = device_token
                            self._save_token()
                            print_success("Device authenticated successfully! (Mock mode)")
                            return True
                print_info(".", end="", flush=True)
                continue
        
        print_error("Authentication timed out. Please try again.")
        return False
    
    def _save_token(self):
        """Save device token to keyring."""
        if self.device_id and self.device_token:
            try:
                token_string = f"{self.device_id}:{self.device_token}"
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token_string)
                logger.debug("Token saved to keyring")
            except Exception as e:
                logger.error(f"Failed to save token to keyring: {e}")
                raise
    
    def logout(self):
        """Logout and clear stored token."""
        if self.device_token:
            try:
                # Revoke token on server
                requests.post(
                    f"{self.api_base}/api/device/revoke",
                    json={"device_id": self.device_id},
                    headers={"Authorization": f"Bearer {self.device_token}"},
                    timeout=10
                )
            except Exception as e:
                logger.debug(f"Could not revoke token on server: {e}")
        
        # Clear local token
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception as e:
            logger.debug(f"Could not delete token from keyring: {e}")
        
        self.device_token = None
        self.device_id = None
        print_success("Logged out successfully")
    
    def get_token(self) -> Optional[str]:
        """Get current device token."""
        return self.device_token
    
    def get_device_id(self) -> Optional[str]:
        """Get current device ID."""
        return self.device_id

